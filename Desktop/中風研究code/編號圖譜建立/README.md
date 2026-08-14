# 個體化腦室編號圖譜生成流程 (ANTs Registration)

本流程使用 [ANTsPy](https://github.com/ANTsX/ANTsPy) 進行 CT 標準空間模板與個體
CT 影像之間的非線性配準 (SyN)，並將標準空間的腦室編號圖譜 (atlas) 投影到每個
個體的 CT 空間，產生**個體化編號圖譜**，供後續腦室分區量化分析使用。

---

## 目錄

- [環境需求](#環境需求)
- [整體流程總覽](#整體流程總覽)
- [資料夾結構](#資料夾結構)
- [Step 1：ANTs SyN 配準（標準空間 → 個體空間）](#step-1ants-syn-配準標準空間--個體空間)
- [Step 2：套用轉換，生成個體化編號圖譜](#step-2套用轉換生成個體化編號圖譜)
- [使用前請確認](#使用前請確認)
- [常見問題](#常見問題)

---

## 環境需求

- Python 3
- [ANTsPy](https://github.com/ANTsX/ANTsPy)（`pip install antspyx`）
- 前置資料：
  - 個體 CT 影像（建議使用已完成顱骨剝離的 CT，見主流程 README 的 Step 2）
  - CT 標準空間模板 `CT_template2.nii.gz`
  - 標準空間腦室編號圖譜 `number_template.nii.gz`

---

## 整體流程總覽

```
個體 CT 影像資料夾                CT 標準空間模板 (CT_template2.nii.gz)
        │                                   │
        └───────────────┬───────────────────┘
                         ▼
        [Step 1] ANTs SyN 配準 (標準模板 → 個體 CT 空間)
                         │
                         ▼
        產生：轉換矩陣 (.mat) ＋ 位移場 (.nii.gz)
                         │
                         ▼
        [Step 2] 套用轉換，將「標準空間編號圖譜」投影到個體空間
                         │
                         ▼
              個體化編號圖譜（每個案例一張）
```

Step 1 的輸出（轉換矩陣、位移場）是 Step 2 的必要輸入，兩步驟需依序執行。

---

## 資料夾結構

```
個體CT影像資料夾/                    # Step 1、2 共用的 fixed 影像（配準目標空間）
  ├── ct1.nii.gz
  ├── ct2.nii.gz
  └── ...

CT_template2.nii.gz                # CT 標準空間模板（Step 1 的 moving image）
number_template.nii.gz             # 標準空間腦室編號圖譜（Step 2 的 moving image）

轉換矩陣與位移場輸出資料夾/           # Step 1 輸出
  ├── warped_ct1.nii.gz            # 配準後的模板影像（僅供檢查配準品質用）
  ├── transform_ct1.mat            # 仿射轉換矩陣
  ├── transform_ct1.nii.gz         # 非線性位移場
  └── ...（每個案例各一組）

個體化編號圖譜輸出資料夾/             # Step 2 最終輸出
  ├── 個體編號圖譜_ct1.nii.gz
  ├── 個體編號圖譜_ct2.nii.gz
  └── ...
```

---

## Step 1：ANTs SyN 配準（標準空間 → 個體空間）

**腳本**：`04_ants_registration.py`

### 功能
將 CT 標準空間模板 (moving) 配準對齊到每一個個體 CT 影像 (fixed)，使用 SyN
非線性配準方法，產生轉換矩陣與位移場，供 Step 2 套用到編號圖譜上。

### 處理流程
1. 讀取個體 CT 影像 (fixed) 與標準空間模板 (moving)
2. 執行 `ants.registration(type_of_transform='SyN')`
3. 輸出配準後的模板影像（可用來目視檢查配準品質）
4. 輸出轉換矩陣 (`.mat`) 與位移場 (`.nii.gz`)，並依案例名稱重新命名

### 主要參數

| 變數 | 說明 |
|---|---|
| `fixed_folder` | 存放所有個體 CT 影像的資料夾 |
| `moving_img` | CT 標準空間模板路徑 |
| `output_folder` | 轉換矩陣、位移場、配準後影像的輸出資料夾 |

### 輸出

```
output_folder/warped_案例名.nii.gz     配準後的模板影像
output_folder/transform_案例名.mat     仿射轉換矩陣
output_folder/transform_案例名.nii.gz  非線性位移場
```

---

## Step 2：套用轉換，生成個體化編號圖譜

**腳本**：`05_apply_atlas_transform.py`

### 功能
讀取 Step 1 產生的轉換矩陣與位移場，將標準空間的腦室編號圖譜套用相同轉換，
形變到每個個體的 CT 空間，產生個體化編號圖譜。

### 處理流程
1. 掃描個體 CT 資料夾，取得所有案例
2. 依案例名稱，自動比對 Step 1 輸出的對應轉換檔案
   （`transform_案例名.nii.gz` / `transform_案例名.mat`）
3. 使用 `ants.apply_transforms()` 將編號圖譜套用轉換，投影到個體空間
4. 輸出個體化編號圖譜

### 主要參數

| 變數 | 說明 |
|---|---|
| `fixed_folder` | 存放所有個體 CT 影像的資料夾（需與 Step 1 使用的一致） |
| `moving_img` | 標準空間腦室編號圖譜路徑 (`number_template.nii.gz`) |
| `transform_dir` | Step 1 輸出的轉換矩陣/位移場所在資料夾 |
| `output_folder` | 個體化編號圖譜輸出資料夾 |

### 輸出

```
output_folder/個體編號圖譜_案例名.nii.gz
```

### 重要技術細節

- **內插方式使用 `nearestNeighbor`**：因為編號圖譜屬於類別型標籤
  (label/segmentation)，數值代表特定腦室分區編號，若使用線性內插會產生
  不存在的中間數值，破壞編號本身的意義，因此必須使用最近鄰內插。
- **轉換套用順序**：`transformlist=[位移場, 仿射矩陣]`，順序需與 Step 1
  `reg['fwdtransforms']` 的輸出順序一致，才能正確還原配準結果。

---

## 使用前請確認

1. **Step 1 與 Step 2 使用的個體 CT 影像資料夾需完全一致**，否則會因檔名對不上
   而找不到對應的轉換矩陣/位移場
2. **檔名命名規則需前後一致**：Step 1 產生 `transform_案例名.mat` /
   `transform_案例名.nii.gz`，Step 2 是依此規則自動比對，若手動調整過檔名，
   兩邊需同步修改
3. 建議先用 1 個案例測試整體流程、並目視檢查 Step 1 輸出的 `warped_*.nii.gz`
   是否配準良好，再批次跑全部案例
4. `ants.registration` 的 SyN 配準運算量較大，批次處理案例數多時建議評估
   執行時間與硬體資源


