#!/bin/bash
#
# 功能：接續顱骨剝離 (Skull Stripping) 後的 CT 影像，執行腦脊髓液 (CSF) 分割
# 前置條件：
#     前一支腳本的輸出底下應有去骨後的 CT 影像：
#     >>輸出資料夾名稱/案例編號_CT.nii.gz
#
# 流程：
#   1. FLIRT 配準：將 MNI 空間的組織機率圖 (PVE) 對齊到個別 CT 空間
#   2. 影像數值平移 (+10) 後，與配準後的 PVE 影像相乘，加強腦室訊號
#   3. FAST 分割：對相乘後的影像做組織分割，得到各類組織的機率圖 (pve_0/1/2)
#   4. 閾值化 pve_1（通常對應 CSF），產生二值化腦室遮罩
#   5. 用遮罩回套到去骨後的 CT，得到最終腦室分割結果
#
# 輸出：
#   統一輸出到 final_seg_dir，檔名為「案例編號_CT.nii.gz」
#
# ===== 使用前請確認 =====
# 1. 已安裝 FSL，且 fslmaths / flirt / fast / bet 指令可直接執行
# 2. 已將對應的 MNI_tissue_weight.nii.gz 等權重檔案放入
#    $FSLDIR/data/standard/tissuepriors 目錄下
# 3. 下方標註「資料夾」的變數，請替換成你自己環境中的實際絕對路徑


export OMP_NUM_THREADS=8

# ===== 可自行修改的參數 =====
bet_ct_dir="顱骨去除完的CT影像資料夾"                         # 前一步驟：去骨後 CT 存放位置
work_root="運算中繼檔案資料夾"                                # 中繼檔案根目錄
final_seg_dir="腦室分割完的CT影像資料夾"                           # 最終腦室分割結果輸出資料夾

mni_tissue_prob="使用附檔中的MNI_tissue_weight.nii.gz"  # MNI 空間組織機率圖，用於flirt影像對位
pve_mat_dir="${work_root}/CT_pve_mat"                          # FLIRT 配準矩陣存放位置
pve_dir="${work_root}/CT_pve"                                  # FLIRT 配準後的 PVE 影像
add_dir="${work_root}/CT_add"                                  # +10 平移後的影像
mul_dir="${work_root}/CT_mul"                                  # 相乘後的影像
fast_dir="${work_root}/CT_fast"                                # FAST 分割輸出
bin_dir="${work_root}/CT_bin"                                  # 二值化遮罩

# FAST 需要的 MNI 參考影像（依你原始指令保留，路徑需自行確認是否正確）
mni_tissue_ref="MNI_tissue_weight.nii.gz"
mni_water_ref="MNI_water_weight.nii.gz"

# ===== 建立所需資料夾 =====
mkdir -p "${pve_dir}" "${pve_mat_dir}" "${add_dir}" "${mul_dir}" "${fast_dir}" "${bin_dir}" "${final_seg_dir}"

time {
    # ===== 掃描去骨後 CT 資料夾，取得所有案例 =====
    ct_files=($(find "${bet_ct_dir}" -maxdepth 1 -type f -name "*_CT.nii.gz"))

    for ct_file in "${ct_files[@]}"; do

        # 從檔名取出案例編號，例如 "案例1_CT.nii.gz" -> "案例1"
        file_name=$(basename "${ct_file}")
        subject_name="${file_name%_CT.nii.gz}"

        echo "===== doing ${subject_name} ====="

        # ---- Step 1: (可選) FLIRT 配準，將 MNI 組織機率圖對齊到個別 CT 空間 ----
        flirt -in "${mni_tissue_prob}" \
               -ref "${ct_file}" \
               -out "${pve_dir}/pve_${subject_name}.nii.gz" \
               -omat "${pve_mat_dir}/pve_mat_${subject_name}.mat" \
               -bins 128 -cost mutualinfo -dof 12 -interp trilinear -nosearch

        # ---- Step 2: 影像數值整體 +10，避免後續相乘時出現負值或 0 值問題 ----
        fslmaths "${ct_file}" -add 10 \
                 "${add_dir}/add_${subject_name}.nii.gz"

        # 與配準後的 PVE 影像相乘，加強腦室區域的對比
        fslmaths "${add_dir}/add_${subject_name}.nii.gz" -mul \
                 "${pve_dir}/pve_${subject_name}.nii.gz" \
                 "${mul_dir}/mul_${subject_name}.nii.gz"

        # ---- Step 3: FAST 組織分割 ----
        # 注意：原始指令中 -A 後面的三個檔案（tissue/water/water 機率圖模板）
        #          需更改fsl/data/standard/tissuepriors中的權重影像
        fast -A "${mni_tissue_ref}" "${mni_water_ref}" "${mni_water_ref}" \
             -t 1 -n 2 -H 0.2 -I 1 -l 10.0 \
             -o "${fast_dir}/${subject_name}" \
             "${mul_dir}/mul_${subject_name}.nii.gz"

        # ---- Step 4: 閾值化 pve_1（通常對應 CSF 組織機率圖），產生二值化遮罩 ----
        fslmaths "${fast_dir}/${subject_name}_pve_1.nii.gz" -thr 0.01 -bin \
                 "${bin_dir}/bin_${subject_name}.nii.gz"

        # ---- Step 5: 用遮罩回套到去骨後的原始 CT，得到最終腦室分割結果 ----
        fslmaths "${ct_file}" -mas \
                 "${bin_dir}/bin_${subject_name}.nii.gz" \
                 "${final_seg_dir}/${subject_name}_CT.nii.gz"

        echo "=== complete ${subject_name} ==="
    done
}