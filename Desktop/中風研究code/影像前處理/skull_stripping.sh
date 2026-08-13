#!/bin/bash
#
# 功能：接續 DICOM→NIFTI 轉檔結果，對每個案例的 CT 影像執行顱骨剝離 (Skull Stripping)
# 前置條件：
#   nifti_root 底下應有如下結構（由前一支 dcm2niix 腳本產生）：
#     nifti_root/
#       ├── 案例1/CT/CT.nii.gz
#       ├── 案例2/CT/CT.nii.gz
#       └── ...
#
# 流程：
#   1. 閾值化 (Threshold)
#   2. 二值化並填補孔洞
#   3. 膨脹再侵蝕 (Closing)
#   4. 平滑後套用遮罩
#   5. BET 去頭骨
#   6. 用 BET 遮罩回套「原始 CT」，得到最終去骨影像
#   7. 確認輸出成功後，刪除該案例的中繼檔案資料夾
#
# 輸出：
#   統一輸出到 final_output_dir，檔名為「案例編號_CT.nii.gz」
#

export OMP_NUM_THREADS=8

time {
    # ===== 可自行修改的參數 =====
    nifti_root="存放NIFTI的資料夾"                        # 前一步驟轉出的 NIFTI 根目錄
    ct_prefix="CT"                                        # dcm2niix 輸出的檔名前綴（對應 -f "CT"）
    work_root="中繼檔案資料夾"           # 中繼檔案存放位置（各步驟過程檔）
    final_output_dir="最終輸出存放資料夾"   # 最終去骨影像統一輸出資料夾

    mkdir -p "${final_output_dir}"

    # ===== 掃描 nifti_root 底下所有案例資料夾 =====
    subject_folders=($(find "${nifti_root}" -mindepth 1 -maxdepth 1 -type d))

    for subject_path in "${subject_folders[@]}"; do

        subject_name=$(basename "${subject_path}")
        ori_ct="${subject_path}/CT/${ct_prefix}.nii.gz"
        case_dir="${work_root}/${subject_name}"
        final_output="${final_output_dir}/${subject_name}_CT.nii.gz"

        # 檢查該案例的 CT nifti 是否存在
        if [ ! -f "${ori_ct}" ]; then
            echo "找不到 CT 影像：${ori_ct}，跳過此案例"
            continue
        fi

        echo "===== build ${subject_name} ====="
        mkdir -p "${case_dir}"
        echo "=== doing ${subject_name} ==="

        # ---- Step 1: 閾值化，只保留 0~100 HU 範圍的組織 ----
        fslmaths "${ori_ct}" -thr 0.000000 -uthr 100.000000 \
                 "${case_dir}/td_${subject_name}.nii.gz"

        # ---- Step 2: 二值化，並填補遮罩內的孔洞 ----
        fslmaths "${case_dir}/td_${subject_name}.nii.gz" -bin \
                 "${case_dir}/bin_${subject_name}.nii.gz"

        fslmaths "${case_dir}/bin_${subject_name}.nii.gz" -bin -fillh \
                 "${case_dir}/bin_${subject_name}.nii.gz"

        # ---- Step 3: 先膨脹再侵蝕 (Closing)，平滑邊緣、封閉小裂縫 ----
        fslmaths "${case_dir}/bin_${subject_name}.nii.gz" -dilD \
                 "${case_dir}/bin_${subject_name}_dil.nii.gz"

        fslmaths "${case_dir}/bin_${subject_name}_dil.nii.gz" -ero \
                 "${case_dir}/bin_${subject_name}_closed.nii.gz"

        # ---- Step 4: 平滑影像後，套用 Step 3 遮罩限制範圍 ----
        fslmaths "${case_dir}/td_${subject_name}.nii.gz" -s 2 \
                 "${case_dir}/smooth_${subject_name}.nii.gz"

        fslmaths "${case_dir}/smooth_${subject_name}.nii.gz" -mas \
                 "${case_dir}/bin_${subject_name}_closed.nii.gz" \
                 "${case_dir}/smooth_${subject_name}.nii.gz"

        # ---- Step 5: 執行 BET 去頭骨 ----
        bet "${case_dir}/smooth_${subject_name}.nii.gz" \
            "${case_dir}/bet_${subject_name}.nii.gz" -R -f 0.1

        fslmaths "${case_dir}/bet_${subject_name}.nii.gz" -bin -fillh \
                 "${case_dir}/bet_bin_${subject_name}.nii.gz"

        # ---- Step 6: 用最終遮罩回套「原始 CT」，統一輸出到 final_output_dir ----
        fslmaths "${ori_ct}" -mas \
                 "${case_dir}/bet_bin_${subject_name}.nii.gz" \
                 "${final_output}"

        # ---- Step 7: 確認最終輸出檔案存在後，清除中繼檔案資料夾 ----
        if [ -f "${final_output}" ]; then
            rm -rf "${case_dir}"
            echo "已清除中繼檔案：${case_dir}"
        else
            echo "最終輸出檔案未產生，保留中繼檔案供除錯：${case_dir}"
        fi

        echo "=== complete ${subject_name} ==="
    done
}