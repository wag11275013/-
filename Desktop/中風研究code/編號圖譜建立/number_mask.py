#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

功能：套用轉換矩陣與位移場，將標準空間編號圖譜投影到個體 CT 空間
說明：
    延續前一支 ANTs 配準腳本產生的「轉換矩陣 (.mat)」與「位移場 (.nii.gz)」，
    將標準空間的編號圖譜 (number_template.nii.gz) 套用這些轉換，
    形變到每一個個體的 CT 空間，產生「個體化編號圖譜」。

輸入：
    - fixed_folder      存放所有個體 CT 影像的資料夾（配準的目標空間，需與
                         前一支配準腳本使用的 fixed 影像一致，才能對到正確的
                         transform 檔案）
    - moving_img         標準空間編號圖譜 (number_template.nii.gz)
    - transform_dir       前一支腳本輸出的轉換矩陣/位移場所在資料夾
                         （檔名格式：transform_案例名.nii.gz / transform_案例名.mat）

輸出：
    - output_folder 底下，每個案例產生一張個體化編號圖譜：
        個體編號圖譜_案例名.nii.gz

注意：
    - interpolator 使用 'nearestNeighbor'，因為編號圖譜屬於類別型標籤
      (label/segmentation)，不能用線性內插，否則會產生不存在的中間數值，
      破壞編號的意義。
"""

import ants
import os
import time


def apply_atlas_transform(fixed_path, moving_path, transform_list, output_path):
    """
    將標準空間編號圖譜，透過指定的轉換套用到單一個體 CT 空間

    參數：
        fixed_path      個體 CT 影像路徑（目標空間）
        moving_path     標準空間編號圖譜路徑
        transform_list  轉換清單 [位移場路徑, 仿射矩陣路徑]
        output_path     輸出的個體化編號圖譜路徑
    """
    fixed = ants.image_read(fixed_path)
    moving = ants.image_read(moving_path)

    warped = ants.apply_transforms(
        fixed=fixed,
        moving=moving,
        transformlist=transform_list,
        interpolator='nearestNeighbor'  # 編號屬於 label/segmentation，須用最近鄰內插
    )

    ants.image_write(warped, output_path)


if __name__ == "__main__":

    # ===== 可自行修改的參數 =====
    fixed_folder = "腦室分割後 CT 影像的資料夾"  # 個體 CT 影像資料夾
    moving_img = "number_template.nii.gz"     # 標準空間編號圖譜
    transform_dir = "ants_registration輸出的轉換檔資料夾"       # 前一步驟輸出的轉換檔資料夾
    output_folder = "每個案例編號遮罩的輸出資料夾" # 輸出資料夾

    os.makedirs(output_folder, exist_ok=True)

    start_time = time.time()

    # 掃描 fixed_folder 底下所有個體 CT 影像
    fixed_files = [f for f in os.listdir(fixed_folder) if f.endswith(".nii.gz")]

    for fixed_file in fixed_files:

        fixed_path = os.path.join(fixed_folder, fixed_file)

        # 取得案例名稱（去除 .nii.gz），對應前一步驟輸出的 transform 檔名
        subject_name = fixed_file.replace(".nii.gz", "")

        warp_field = os.path.join(transform_dir, f"transform_{subject_name}.nii.gz")
        affine_mat = os.path.join(transform_dir, f"transform_{subject_name}.mat")

        # 檢查對應的轉換檔是否存在，避免中斷整體流程
        if not (os.path.exists(warp_field) and os.path.exists(affine_mat)):
            print(f"找不到 {subject_name} 對應的轉換檔案，跳過")
            continue

        output_path = os.path.join(output_folder, f"個體編號圖譜_{subject_name}.nii.gz")

        print(f"Processing {subject_name}...")

        apply_atlas_transform(
            fixed_path=fixed_path,
            moving_path=moving_img,
            transform_list=[warp_field, affine_mat],  # 順序：位移場 → 仿射矩陣
            output_path=output_path
        )

        print(f"  → 已輸出：{output_path}")

    end_time = time.time()
    print(f"Total time: {end_time - start_time:.2f} seconds")