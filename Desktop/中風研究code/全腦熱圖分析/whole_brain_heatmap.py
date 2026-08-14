#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能：腦部 CT 局部數值分布位移熱圖 (Distribution Shift Heatmap) 批次生成

說明：
    以每個腦室編號 (label) 的中心 voxel 為球心，取半徑 SPHERE_RADIUS_MM 的 3D 球型
    區域，統計該區域內個體 CT 數值分布，並與「健康資料集」中相同 label 的分布做
    比較，計算兩者之間的「分布位移量 (shift)」。

    接著利用左右對稱 mapping，排除單側屬正常變異、對側才是真正病灶造成誤判的情況，
    並排除特定 x 軸區間（常鄰接腦室/CSF，容易因水的訊號造成誤判）的 label，
    最終將篩選出的可疑病灶區域，以熱圖 (heatmap) 形式輸出。

輸入（每個案例各一組）：
    - 個體 CT 影像：已完成顱骨剝離、CSF/腦室分割等前處理的 CT
    - 個體編號遮罩：由 ANTs 配準流程產生的個體化腦室編號圖譜

輸入（全域共用，只需載入一次）：
    - 健康資料集直方圖 (.h5)：各腦室編號在健康族群中的 CT 數值分布
    - 左右對稱編號 mapping (.json)：用於左右腦比對，排除雙側變異
    - 排除編號清單 (.json)：排除易受水（CSF）干擾、容易誤判的區域

輸出：
    - 每個案例一張熱圖 (.nii.gz)，標示可疑病灶區域的分布位移程度
"""

import os
import json
import time
import math

import h5py
import numpy as np
import nibabel as nib
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import Normalize
from scipy.ndimage import gaussian_filter, gaussian_filter1d
from scipy.stats import skew, kurtosis
from multiprocessing import Pool, cpu_count
from tqdm import tqdm


# ============================================================
# 可自行修改的參數
# ============================================================
SPHERE_RADIUS_MM = 10          # 球型取樣區域半徑 (mm)
SHIFT_DIFF_THRESHOLD = 0.9     # 左右側 shift 差異門檻，超過才視為可疑病灶
MIN_SHIFT_MAGNITUDE = 2.5      # shift 絕對值門檻，兩側都大於此值視為對稱性異常而非病灶
ENABLE_VISUALIZATION = False   # 是否逐張顯示切片疊圖（批次處理大量案例建議設 False）

# ---- 輸入路徑 ----
individual_image_dir = "個體CT影像資料夾（已完成前處理）"
individual_mask_dir = "個體編號遮罩資料夾（ANTs流程產生的個體化編號圖譜）"
healthy_hdf5_path = f"number_ct_histogram_dataset_{SPHERE_RADIUS_MM}mm_whole_image_final.h5" # 健康資料集(可選擇不同半徑)
mapping_json_path = "label_left_right_mapping_reg1_bidirectional.json"  # 左右對稱編號 mapping
exclude_json_path = "excluded_labels_x40_50.json"                      # 排除編號清單（x軸40~50區間）

# ---- 輸出路徑 ----
output_dir = "C:/data/ct_stroke_heatmap"

# ---- 個體編號遮罩檔名規則（依 ANTs 流程輸出調整，{subject} 會替換成案例名稱）----
mask_filename_pattern = "number_{subject}.nii.gz"


# ============================================================
# 共用工具函式
# ============================================================
def create_sphere_template(radius_x, radius_y, radius_z):
    """建立以 voxel 為單位的 3D 球型取樣模板（布林遮罩）"""
    shape = (2 * radius_x + 1, 2 * radius_y + 1, 2 * radius_z + 1)
    center = (radius_x, radius_y, radius_z)
    mask = np.zeros(shape, dtype=bool)
    for x in range(shape[0]):
        for y in range(shape[1]):
            for z in range(shape[2]):
                dx = (x - center[0]) / radius_x
                dy = (y - center[1]) / radius_y
                dz = (z - center[2]) / radius_z
                if dx * dx + dy * dy + dz * dz <= 1:
                    mask[x, y, z] = True
    return mask


def extract_sphere(image, center, template):
    """從 image 中，以 center 為球心，依 template 形狀取出球型區域內的數值"""
    rx, ry, rz = template.shape[0] // 2, template.shape[1] // 2, template.shape[2] // 2
    cx, cy, cz = center
    x1, y1, z1 = cx - rx, cy - ry, cz - rz
    x2, y2, z2 = cx + rx + 1, cy + ry + 1, cz + rz + 1

    if x1 < 0 or y1 < 0 or z1 < 0 or x2 > image.shape[0] or y2 > image.shape[1] or z2 > image.shape[2]:
        return None

    region = image[x1:x2, y1:y2, z1:z2]
    return region[template]


def compute_shift(args, healthy_hist_dict, bins, bin_centers, image_data, template):
    """
    計算單一 label 區域，個體與健康資料集之間的 CT 數值分布位移量 (shift)

    回傳：(label, shift, values, is_bad_peak)，若該 label 不符合計算條件則回傳 None
    """
    label, center = args
    if label not in healthy_hist_dict:
        return None

    values = extract_sphere(image_data, center, template)
    if values is None:
        return None
    values = values[values > 10]

    # 球型區域內有效 voxel 比例過低（例如貼近影像邊界），視為不可靠
    if len(values) / np.sum(template) < 0.5:
        return None

    # 分布形狀異常（過度尖峰或嚴重左偏），視為不可靠，排除
    if kurtosis(values) > 1.5 or skew(values) < -0.8:
        return None

    hist, _ = np.histogram(values, bins=bins)
    pct = hist / np.sum(hist) * 100
    smoothed = gaussian_filter1d(pct, sigma=1)

    main_peak_idx = np.argmax(smoothed)
    left_sum = np.sum(smoothed[max(0, main_peak_idx - 2):main_peak_idx])
    right_sum = np.sum(smoothed[main_peak_idx + 3:])
    main_sum = np.sum(smoothed[max(0, main_peak_idx - 2):main_peak_idx + 3])

    outside_ratio = (left_sum + right_sum) / (left_sum + right_sum + main_sum + 1e-5)
    is_bad_peak = outside_ratio > 0.35

    healthy_hist = healthy_hist_dict[label]
    healthy_pct = healthy_hist / np.sum(healthy_hist) * 100
    healthy_mean = np.average(bin_centers, weights=healthy_pct)
    if healthy_mean > 32:
        return None

    unique_vals, counts = np.unique(values, return_counts=True)
    subject_mean = np.average(unique_vals, weights=counts)
    if subject_mean > 40:
        return None

    shift = healthy_mean - subject_mean
    return (label, shift, values, is_bad_peak)


# ---- multiprocessing 專用：每個子行程啟動時先取得共用唯讀資料，避免每個任務重複傳遞大型陣列 ----
_worker_ctx = {}


def _init_worker(healthy_hist_dict, bins, bin_centers, image_data, template):
    global _worker_ctx
    _worker_ctx = {
        "healthy_hist_dict": healthy_hist_dict,
        "bins": bins,
        "bin_centers": bin_centers,
        "image_data": image_data,
        "template": template,
    }


def _compute_shift_worker(args):
    return compute_shift(args, **_worker_ctx)


def filter_opposite_lesion(results, label_mapping, excluded_labels,
                            global_template, shift_diff_threshold, min_shift_magnitude):
    """
    利用左右對稱 mapping，排除單側屬正常變異、對側才是真正病灶的情況，
    並套用多項門檻篩選出真正可疑的病灶 label。
    """
    label_shift_dict = {label: shift for label, shift, _, _ in results}
    label_val_dict = {label: vals for label, _, vals, _ in results}
    label_peak_flag = {label: is_bad for label, _, _, is_bad in results}

    filtered_results = []
    skip_labels = set()

    for label, shift, values, is_bad in results:

        if label in skip_labels or label in excluded_labels:
            continue

        opp = label_mapping.get(label)
        if opp is None or opp in excluded_labels:
            continue

        # 若對稱 label 本身沒有計算結果，往相鄰編號尋找可替代的對稱區域
        candidate_label = None
        if opp in label_shift_dict and opp not in excluded_labels:
            candidate_label = opp
        else:
            for delta in range(1, 11):  # 往上下最多搜尋 10 個編號範圍內的替代區域
                for alt_label in [opp - delta, opp + delta]:
                    if alt_label in label_shift_dict and alt_label not in excluded_labels:
                        candidate_label = alt_label
                        print(f"[Fallback] Replace missing opp_label {opp} with nearby label {alt_label} for label {label}")
                        break
                if candidate_label is not None:
                    break

        if candidate_label is None:
            continue

        opp = candidate_label
        if opp in skip_labels:
            continue

        if label_peak_flag.get(label, True) or label_peak_flag.get(opp, True):
            skip_labels.add(label)
            skip_labels.add(opp)
            continue

        opp_shift = label_shift_dict[opp]
        opp_vals = label_val_dict.get(opp)

        if len(values) < 20 or opp_vals is None or len(opp_vals) < 20:
            skip_labels.add(label)
            skip_labels.add(opp)
            continue

        if len(opp_vals) / np.sum(global_template) < 0.5:
            skip_labels.add(label)
            skip_labels.add(opp)
            continue

        if abs(shift) > min_shift_magnitude and abs(opp_shift) > min_shift_magnitude:
            skip_labels.add(label)
            skip_labels.add(opp)
            continue

        if shift < -2.0 or opp_shift < -2.0:
            skip_labels.add(label)
            skip_labels.add(opp)
            continue

        if -1.0 < shift < 1.0 and -1.0 < opp_shift < 1.0:
            skip_labels.add(label)
            skip_labels.add(opp)
            continue

        shift_diff = abs(shift - opp_shift)
        skip_labels.add(label)
        skip_labels.add(opp)

        if shift_diff > shift_diff_threshold:
            if shift >= opp_shift:
                filtered_results.append((label, shift_diff, values))
            else:
                filtered_results.append((opp, shift_diff, opp_vals))

    return filtered_results


def build_heatmap_fill(mask_data, result_list, image_shape, sigma=2):
    """依篩選後的可疑 label 清單，把 shift 值填回對應 voxel，建立熱圖"""
    heatmap = np.zeros(image_shape, dtype=np.float32)
    label_to_shift = {label: shift for label, shift, *_ in result_list}
    label_mask = np.isin(mask_data, list(label_to_shift.keys()))
    coords = np.argwhere(label_mask)
    for x, y, z in coords:
        label = int(mask_data[x, y, z])
        shift = label_to_shift.get(label)
        if shift is not None:
            heatmap[x, y, z] = shift
    heatmap = np.clip(heatmap, 0, 6)
    heatmap[:, :, :6] = 0
    heatmap[:, :, 20:] = 0
    if sigma > 0:
        heatmap = gaussian_filter(heatmap, sigma=sigma)
    return heatmap


def visualize_heatmap(image_data, heatmap, vmin=0, vmax=5, cmap_name="YlOrRd"):
    """逐張 z 軸切片，把熱圖疊加在原始 CT 影像上顯示（除錯/檢查用）"""
    cmap = cm.get_cmap(cmap_name)
    norm = Normalize(vmin=vmin, vmax=vmax)
    image_mask = image_data > 0
    for z_index in range(image_data.shape[2]):
        slice_image = image_data[:, :, z_index]
        slice_heatmap = heatmap[:, :, z_index]
        slice_mask = image_mask[:, :, z_index]
        masked_heatmap = np.ma.masked_where(~slice_mask, slice_heatmap)
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.imshow(slice_image.T, cmap="gray", origin="lower")
        ax.imshow(masked_heatmap.T, cmap=cmap, norm=norm, origin="lower", alpha=0.6)
        ax.set_title(f"Heatmap - Z slice {z_index}", fontsize=15)
        ax.axis("off")
        cbar = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("Distribution Shift", rotation=270, labelpad=15)
        plt.show()


# ============================================================
# 單一案例處理流程
# ============================================================
def process_subject(subject_name, image_path, mask_path,
                     healthy_hist_dict, bins, bin_centers,
                     label_mapping, excluded_labels):
    """對單一案例執行完整的分布位移熱圖生成流程"""

    print(f"\n=== Processing {subject_name} ===")

    # ---- Step 1: 讀取影像與遮罩 ----
    start_time = time.time()
    image_img = nib.load(image_path)
    image_data = image_img.get_fdata()

    # 個體整體 CT 數值校正：把個體影像整體平移至與健康資料集整體平均值一致，
    # 避免不同案例間的整體亮度差異，干擾後續 label 層級的分布比較
    subject_vals = image_data[image_data > 0]
    subject_global_mean = np.mean(subject_vals)

    healthy_means = []
    for hvals in healthy_hist_dict.values():
        if np.sum(hvals) == 0 or np.any(np.isnan(hvals)):
            continue
        pct = hvals / np.sum(hvals)
        healthy_means.append(np.average(bin_centers, weights=pct))
    healthy_global_mean = np.mean(healthy_means)

    correction = healthy_global_mean - subject_global_mean
    image_data[image_data > 0] += correction
    print(f"[Correction Applied] Shifted by {correction:.2f} "
          f"(subject mean {subject_global_mean:.2f} -> healthy mean {healthy_global_mean:.2f})")

    voxel_sizes = image_img.header.get_zooms()
    mask_img = nib.load(mask_path)
    mask_data = mask_img.get_fdata()
    print(f"data loading: {time.time() - start_time:.2f}s")

    # ---- Step 2: 找出每個 label 的中心 voxel、建立球型取樣模板 ----
    start_time = time.time()
    label_centers = {}
    coords_all = np.argwhere(mask_data > 0)
    for x, y, z in coords_all:
        label = int(mask_data[x, y, z])
        if label not in label_centers:
            label_centers[label] = (x, y, z)

    valid_mask = image_data > 0
    valid_label_set = set(mask_data[valid_mask].astype(int))

    radius_voxels = [
        max(1, int(SPHERE_RADIUS_MM / voxel_sizes[0])),
        max(1, int(SPHERE_RADIUS_MM / voxel_sizes[1])),
        max(1, int(SPHERE_RADIUS_MM / voxel_sizes[2])),
    ]
    template = create_sphere_template(*radius_voxels)
    print(f"find label and center: {time.time() - start_time:.2f}s")

    args_list = [(label, center) for label, center in label_centers.items()
                 if label in valid_label_set]

    # ---- Step 3: 平行計算每個 label 的分布位移量 ----
    start_time = time.time()
    results = []
    with Pool(
        processes=max(1, cpu_count() - 1),
        initializer=_init_worker,
        initargs=(healthy_hist_dict, bins, bin_centers, image_data, template),
    ) as pool:
        for res in tqdm(pool.imap_unordered(_compute_shift_worker, args_list, chunksize=200),
                         total=len(args_list), desc=f"{subject_name} - Parallel Shift"):
            if res is not None:
                results.append(res)
    print(f"multiprocessing: {time.time() - start_time:.2f}s")

    # ---- Step 4: 左右對稱排除 + 篩選可疑病灶 ----
    start_time = time.time()
    filtered_results = filter_opposite_lesion(
        results, label_mapping, excluded_labels,
        template, SHIFT_DIFF_THRESHOLD, MIN_SHIFT_MAGNITUDE
    )
    print(f"opposite lesion exclusive: {time.time() - start_time:.2f}s")

    # ---- Step 5: 建立並輸出熱圖 ----
    heatmap = build_heatmap_fill(mask_data, filtered_results, image_data.shape, sigma=1)
    max_shift = math.ceil(np.max(heatmap)) if np.max(heatmap) > 0 else 1
    print(f"max shift: {max_shift}")

    if ENABLE_VISUALIZATION:
        visualize_heatmap(image_data, heatmap, vmin=0, vmax=max_shift, cmap_name="YlOrRd")

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{subject_name}_shift_heatmap.nii.gz")
    heatmap_nifti = nib.Nifti1Image(heatmap, affine=image_img.affine, header=image_img.header)
    nib.save(heatmap_nifti, output_path)
    print(f"Heatmap saved to: {output_path}")


# ============================================================
# 主流程：批次處理資料夾內所有案例
# ============================================================
if __name__ == "__main__":

    # ---- 載入健康資料集（只需載入一次，所有案例共用）----
    start_time = time.time()
    with h5py.File(healthy_hdf5_path, "r", libver="latest") as h5f:
        bins = h5f["bins"][:]
        healthy_hist_dict = {int(key): h5f[key][:] for key in h5f.keys() if key != "bins"}
    bin_centers = 0.5 * (bins[:-1] + bins[1:])
    print(f"healthy dataset loading: {time.time() - start_time:.2f}s")

    # ---- 載入左右對稱 mapping 與排除清單（只需載入一次）----
    with open(mapping_json_path, "r") as f:
        label_mapping = {int(k): int(v) for k, v in json.load(f).items()}
    with open(exclude_json_path, "r") as f:
        excluded_labels = set(json.load(f))

    # ---- 掃描個體 CT 影像資料夾，取得所有案例 ----
    image_files = [f for f in os.listdir(individual_image_dir) if f.endswith(".nii.gz")]

    for image_file in tqdm(image_files, desc="Pipeline", unit="case"):

        subject_name = image_file.replace(".nii.gz", "")
        image_path = os.path.join(individual_image_dir, image_file)
        mask_path = os.path.join(individual_mask_dir, mask_filename_pattern.format(subject=subject_name))

        if not os.path.exists(mask_path):
            print(f"[SKIP] 找不到 {subject_name} 對應的個體編號遮罩：{mask_path}")
            continue

        process_subject(
            subject_name=subject_name,
            image_path=image_path,
            mask_path=mask_path,
            healthy_hist_dict=healthy_hist_dict,
            bins=bins,
            bin_centers=bin_centers,
            label_mapping=label_mapping,
            excluded_labels=excluded_labels,
        )

    print("\nAll processing completed.")