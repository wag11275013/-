# 腦部 CT 局部數值分布位移熱圖生成 (Distribution Shift Heatmap)

以每個腦室編號 (label) 的中心 voxel 為球心，取一定半徑的 3D 球型區域，統計該區域內
個體 CT 數值分布，並與「健康資料集」中相同 label 的分布做比較，計算兩者之間的分布
位移量 (shift)。透過左右對稱比對排除雙側正常或變異造成的誤判，並排除容易受腦脊髓液
(CSF) 干擾的區域，最終將篩選出的可疑病灶區域以熱圖 (heatmap) 形式輸出。

> 本說明以 **Linux 環境**為執行對象。

---

## 目錄

- [環境需求](#環境需求)
- [安裝步驟](#安裝步驟)
- [資料集說明](#資料集說明)
- [資料夾結構](#資料夾結構)
- [輸入資料需求](#輸入資料需求)
- [使用方式](#使用方式)
- [主要參數說明](#主要參數說明)
- [輸出結果](#輸出結果)
- [常見問題](#常見問題)

---

## 環境需求

- **作業系統**：Linux（Ubuntu 或其他發行版皆可）
- **Python**：3.8 以上
- **相依套件**：
  - `nibabel`
  - `numpy`
  - `h5py`
  - `scipy`
  - `tqdm`
  - `matplotlib`

多核心平行運算使用 Python 內建的 `multiprocessing`，不需額外安裝。

---

## 安裝步驟



# 安裝相依套件
pip install nibabel numpy h5py scipy tqdm matplotlib
```


```bash
export MPLBACKEND=Agg
```

批次處理大量案例時，建議保持 `ENABLE_VISUALIZATION = False`（預設值），
僅在檢查單一案例結果時才開啟。

---

## 資料集說明

本專案提供健康資料集直方圖，依「球型取樣半徑」分為 4 個檔案：

| 半徑 (mm) | 檔名 |
|---|---|
| 4  | `number_ct_histogram_dataset_4mm_whole_image_final.h5` |
| 6  | `number_ct_histogram_dataset_6mm_whole_image_final.h5` |
| 8  | `number_ct_histogram_dataset_8mm_whole_image_final.h5` |
| 10 | `number_ct_histogram_dataset_10mm_whole_image_final.h5` |

**每個 `.h5` 檔案內容**：
- `bins`：CT 數值分布的直方圖區間邊界
- 其餘 key（腦室編號）：對應該編號區域，在健康族群中的 CT 數值直方圖統計

> ⚠️ **半徑必須對應一致**：程式內 `SPHERE_RADIUS_MM` 參數，須與所選用的健康資料集
> 檔名中的半徑一致（例如使用 10mm 資料集，`SPHERE_RADIUS_MM` 需設為 `10`），
> 否則球型取樣範圍與健康資料集的統計基礎會不一致，導致比較結果失真。

---

## 資料夾結構

以下為建議的專案目錄結構（依實際上傳到 GitHub 的檔案調整）：

```
專案根目錄/
├── ct_stroke_heatmap_batch.py                          # 主程式
├── datasets/                                            # 健康資料集（4 種半徑）
│   ├── number_ct_histogram_dataset_4mm_whole_image_final.h5
│   ├── number_ct_histogram_dataset_6mm_whole_image_final.h5
│   ├── number_ct_histogram_dataset_8mm_whole_image_final.h5
│   └── number_ct_histogram_dataset_10mm_whole_image_final.h5
├── label_left_right_mapping_reg1_bidirectional.json     # 左右對稱編號 mapping
├── excluded_labels_x40_50.json                          # 排除編號清單
└── README.md
```

輸入的個體 CT 影像與個體編號遮罩，建議另外存放在自己的資料目錄，不需放入
GitHub repo（通常屬於受保護的病人資料，不應公開上傳）。

---

## 輸入資料需求

執行本程式前，需先完成前處理流程，取得以下資料（可參考本系列其他 README 的
Step 1–5）：

| 資料 | 說明 | 對應前處理階段 |
|---|---|---|
| 個體 CT 影像 | 已完成顱骨剝離、CSF/腦室分割等前處理的 CT | 主流程 Step 1–3 |
| 個體編號遮罩 | 由 ANTs 配準流程產生的個體化腦室編號圖譜 | ANTs 流程 Step 1–2 |
| 健康資料集 (.h5) | 對應所選半徑的健康族群 CT 數值分布 | 隨 repo 提供，見上方資料集說明 |
| 左右對稱編號 mapping (.json) | 用於左右腦比對，排除雙側正常變異 | 隨 repo 提供 |
| 排除編號清單 (.json) | 排除易受 CSF 干擾、容易誤判的區域 | 隨 repo 提供 |

---

## 使用方式

1. 打開 `whole_brain_heatmap.py`，修改檔案上方「可自行修改的參數」區塊：

```python
SPHERE_RADIUS_MM = 10   # 需與所選用的健康資料集半徑一致

individual_image_dir = "/path/to/個體CT影像資料夾"
individual_mask_dir = "/path/to/個體編號遮罩資料夾"
healthy_hdf5_path = "/path/to/datasets/number_ct_histogram_dataset_10mm_whole_image_final.h5"
mapping_json_path = "/path/to/label_left_right_mapping_reg1_bidirectional.json"
exclude_json_path = "/path/to/excluded_labels_x40_50.json"

output_dir = "/path/to/輸出熱圖資料夾"
```

2. 於 Linux 終端機執行：

```bash
python3 ct_stroke_heatmap_batch.py
```

3. 程式會自動掃描 `individual_image_dir` 底下所有案例，逐一計算並輸出熱圖，
   終端機會顯示每個案例的處理進度與各步驟耗時。

---

## 主要參數說明

| 參數 | 說明 |
|---|---|
| `SPHERE_RADIUS_MM` | 球型取樣區域半徑 (mm)，需與健康資料集半徑一致 |
| `SHIFT_DIFF_THRESHOLD` | 左右側 shift 差異門檻，超過此值才視為可疑病灶 |
| `MIN_SHIFT_MAGNITUDE` | shift 絕對值門檻，兩側都超過視為對稱性異常而非病灶，予以排除 |
| `ENABLE_VISUALIZATION` | 是否逐張顯示切片疊圖，批次處理大量案例建議關閉 |
| `mask_filename_pattern` | 個體編號遮罩的檔名規則，需與 ANTs 流程輸出的實際檔名對應 |

---

## 輸出結果

每個案例會在 `output_dir` 底下產生一張熱圖：

```
output_dir/案例名稱_shift_heatmap.nii.gz
```

熱圖數值代表該區域相對於健康資料集的分布位移量，數值越高代表與健康族群的
差異越大，可搭配原始 CT 影像疊圖檢視可疑病灶位置。
