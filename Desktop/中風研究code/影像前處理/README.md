# CT 影像前處理流程 (DICOM → NIfTI → 顱骨剝離 → CSF/腦室分割)

本專案提供一套完整的 CT 影像前處理批次腳本，涵蓋從原始 DICOM 資料到最終腦脊髓液
(CSF) / 腦室分割結果的三個階段。所有腳本皆採批次處理設計，可自動掃描案例資料夾並
逐一執行，適合大量案例的自動化處理。

---

## 目錄

- [環境需求](#環境需求)
- [整體流程總覽](#整體流程總覽)
- [資料夾結構](#資料夾結構)
- [Step 1：DICOM 轉 NIfTI](#step-1dicom-轉-nifti)
- [Step 2：顱骨剝離 (Skull Stripping)](#step-2顱骨剝離-skull-stripping)
- [Step 3：CSF / 腦室分割](#step-3csf--腦室分割)
- [使用前請確認](#使用前請確認)
- [常見問題](#常見問題)

---

## 環境需求

- **dcm2niix**：DICOM 轉 NIfTI 工具
- **FSL (FMRIB Software Library)**：需可直接呼叫以下指令
  - `fslmaths`
  - `bet`
  - `flirt`
  - `fast`
- Linux / macOS 環境（腳本使用 Bash 撰寫）
- 建議先設定 `OMP_NUM_THREADS` 以控制平行運算的執行緒數量

---

## 整體流程總覽

```
原始 DICOM 資料
      │
      ▼
[Step 1] dcm2niix 轉檔  ──────────────▶ 案例/CT/CT.nii.gz
      │
      ▼
[Step 2] 顱骨剝離 (BET pipeline) ─────▶ 案例編號_CT.nii.gz（去骨後統一輸出）
      │
      ▼
[Step 3] CSF / 腦室分割 ──────────────▶ 案例編號_CT.nii.gz（分割後統一輸出）
```

每一階段的輸出資料夾，都是下一階段的輸入來源，三支腳本可依序串接執行。

---

## 資料夾結構

以下為執行完整流程後，各階段輸出的建議資料夾結構：

```
存放DICOM的資料夾/
  ├── 案例1/CT/*.dcm
  ├── 案例2/CT/*.dcm
  └── ...

存放NIFTI的資料夾/            # Step 1 輸出
  ├── 案例1/CT/CT.nii.gz
  ├── 案例2/CT/CT.nii.gz
  └── ...

顱骨去除完的CT影像資料夾/      # Step 2 最終輸出
  ├── 案例1_CT.nii.gz
  ├── 案例2_CT.nii.gz
  └── ...

腦室分割完的CT影像資料夾/      # Step 3 最終輸出
  ├── 案例1_CT.nii.gz
  ├── 案例2_CT.nii.gz
  └── ...
```

---

## Step 1：DICOM 轉 NIfTI

**腳本**：`01_dicom_to_nifti.sh`

### 功能
掃描「輸入根目錄」底下的每個案例資料夾，尋找其中的 `CT` 子目錄，使用
`dcm2niix` 將 DICOM 影像轉換為 NIfTI 格式。

### 主要參數

| 變數 | 說明 |
|---|---|
| `input_root` | DICOM 來源根目錄 |
| `output_root` | NIfTI 輸出根目錄 |
| `output_prefix` | 輸出檔名前綴（預設 `CT`） |

### 輸出
```
output_root/案例編號/CT/CT.nii.gz
```

若某案例資料夾內找不到 `CT` 子目錄，會印出警告並跳過，不中斷整體流程。

---

## Step 2：顱骨剝離 (Skull Stripping)

**腳本**：`02_skull_stripping.sh`

### 功能
接續 Step 1 的 NIfTI 輸出，對每個案例執行顱骨剝離，取得僅保留腦組織的 CT 影像。

### 處理流程

1. **閾值化 (Threshold)**：保留 0–100 HU 範圍的組織
2. **二值化 + 填補孔洞 (Binary + Fill holes)**：產生初步遮罩
3. **膨脹再侵蝕 (Closing)**：平滑遮罩邊緣、封閉小裂縫
4. **平滑 + 套用遮罩**：降低雜訊，避免干擾 BET 結果
5. **BET 去頭骨**：`bet -R -f 0.1`
6. **遮罩回套原始 CT**：將 BET 遮罩套用回原始（未平滑）CT，得到最終去骨影像
7. **清除中繼檔案**：確認最終輸出成功後，自動刪除該案例的過程檔案，節省硬碟空間

### 主要參數

| 變數 | 說明 |
|---|---|
| `nifti_root` | Step 1 輸出的 NIfTI 根目錄 |
| `work_root` | 中繼檔案暫存資料夾（跑完會自動清除） |
| `final_output_dir` | 最終去骨影像統一輸出資料夾 |

### 輸出
```
final_output_dir/案例編號_CT.nii.gz
```

---

## Step 3：CSF / 腦室分割

**腳本**：`03_csf_segmentation.sh`

### 功能
接續 Step 2 去骨後的 CT 影像，透過 FLIRT 配準 + FAST 組織分割，取得 CSF
（腦脊髓液／腦室）分割結果。

### 處理流程

1. **FLIRT 配準**：將 MNI 空間的組織機率圖 (PVE) 對齊到個別 CT 空間
2. **數值平移 (+10)**：避免後續相乘時出現負值或 0 值
3. **影像相乘**：平移後影像與配準後 PVE 相乘，加強腦室區域對比
4. **FAST 組織分割**：對相乘後影像分割，取得各組織機率圖（`pve_0/1/2`）
5. **閾值化 `pve_1`**：`-thr 0.01 -bin`，產生 CSF 二值化遮罩
6. **遮罩回套原始 CT**：將遮罩套用回去骨後的 CT，得到最終分割結果

### 主要參數

| 變數 | 說明 |
|---|---|
| `bet_ct_dir` | Step 2 輸出的去骨後 CT 資料夾 |
| `work_root` | 中繼檔案根目錄（PVE、相乘、FAST、二值化遮罩） |
| `final_seg_dir` | 最終腦室分割結果輸出資料夾 |
| `mni_tissue_prob` | 用於 FLIRT 配準的 MNI 組織機率圖路徑 |

### 輸出
```
final_seg_dir/案例編號_CT.nii.gz
```

---

## 使用前請確認

1. **已安裝 FSL**，且 `fslmaths`、`flirt`、`fast`、`bet` 指令可於終端機直接執行
2. **FAST 使用的權重檔案**：`fast -A` 讀取的是
   `$FSLDIR/data/standard/tissuepriors` 目錄下的權重檔，**不是**腳本內變數指定的路徑。
   若需更換權重，請直接替換該目錄下的檔案，而非修改腳本中的變數。
3. 腳本中標註「XX資料夾」的變數，請替換成自己環境中的**實際絕對路徑**
4. 建議先用 1 個案例測試整條流程無誤後，再批次跑全部案例

