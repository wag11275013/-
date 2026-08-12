#!/bin/bash
#
# 功能：批次將 DICOM 資料夾轉換成 NIFTI 格式
# 說明：
#   1. 掃描「輸入根目錄」底下的每一個子資料夾（通常代表一個病人/一個案例）
#   2. 檢查該子資料夾內是否存在名為 "CT" 的子目錄
#   3. 若存在，則呼叫 dcm2niix 將其轉換成 NIFTI，輸出到對應的「輸出根目錄」位置
#   4. 若不存在，則印出警告訊息，方便之後手動檢查
#

time {
    # ===== 可自行修改的參數 =====
    input_root="存放DICOM的資料夾"      # DICOM 來源根目錄
    output_root="存放NIFTI的資料夾"     # NIFTI 輸出根目錄
    output_prefix="CT"                  # 輸出檔名前綴（也用來當作子資料夾名稱）

    # ===== 取得輸入根目錄下所有第一層子資料夾 =====
    subject_folders=($(find "${input_root}" -mindepth 1 -maxdepth 1 -type d))

    # ===== 逐一處理每個病人/案例資料夾 =====
    for subject_path in "${subject_folders[@]}"; do
        subject_name=$(basename "${subject_path}")
        ct_dicom_dir="${subject_path}/CT"

        if [ -d "${ct_dicom_dir}" ]; then
            # 建立對應的輸出資料夾
            output_folder="${output_root}/${subject_name}/${output_prefix}"
            mkdir -p "${output_folder}"

            # 執行 dcm2niix 轉檔
            dcm2niix -o "${output_folder}" -f "${output_prefix}" "${ct_dicom_dir}"
        else
            # 找不到 CT 資料夾時，印出警告方便追蹤
            echo "找不到 CT 資料夾：${ct_dicom_dir}"
        fi
    done
}

