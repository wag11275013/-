#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

功能：ANTs SyN 非線性配準 (Registration)
說明：
    將「CT 標準空間模板」(moving image) 配準對齊到「個體 CT 影像」(fixed image)，
    產生：
      1. 配準後的影像 (warped image)
      2. 轉換矩陣 (.mat，仿射/線性轉換部分)
      3. 位移場 (.nii.gz，非線性形變場)

    這些轉換矩陣與位移場之後可用來將標準空間的腦室編號圖譜 (atlas)
    轉換到每個個體的 CT 空間，建立個體化的腦室編號圖譜。

輸入：
    - fixed_folder：存放所有「個體 CT 影像」的資料夾（會逐一讀取內含所有 .nii.gz）
    - moving_img：CT 標準空間模板 (CT_template2.nii.gz)

輸出：
    - output_folder 底下，每個案例會產生：
        warped_案例名.nii.gz      配準後的模板影像（已對齊到個體空間）
        transform_案例名.mat      仿射轉換矩陣
        transform_案例名.nii.gz   非線性位移場
"""

import ants
import os
import shutil
import time


def ants_syn_registration(fixed_path, moving_path, output_dir, transform_type='SyN'):
    """
    對單一案例執行 ANTs SyN 配準

    參數：
        fixed_path     個體 CT 影像路徑（配準的目標空間）
        moving_path    標準空間模板路徑（要被配準/形變的影像）
        output_dir     輸出資料夾
        transform_type 配準類型，預設 'SyN'（非線性形變配準）

    輸出：
        將配準後影像、轉換矩陣 (.mat)、位移場 (.nii.gz) 存到 output_dir
    """
    os.makedirs(output_dir, exist_ok=True)

    # 取得案例名稱（去除副檔名），用來命名輸出檔案
    fixed_name = os.path.splitext(os.path.basename(fixed_path))[0]
    fixed_name = fixed_name.replace(".nii", "")  # 若原檔名為 .nii.gz，需再去一次副檔名

    # 讀取影像
    fixed = ants.image_read(fixed_path)
    moving = ants.image_read(moving_path)

    # 執行 ANTs 配準（標準模板 → 個體 CT 空間）
    reg = ants.registration(
        fixed=fixed,
        moving=moving,
        type_of_transform=transform_type
    )

    # ---- 儲存配準後的模板影像（已對齊到個體 CT 空間） ----
    warped_image_path = os.path.join(output_dir, f"warped_{fixed_name}.nii.gz")
    ants.image_write(reg['warpedmovout'], warped_image_path)

    # ---- 儲存轉換矩陣與位移場，並依案例名稱重新命名 ----
    for tf in reg['fwdtransforms']:
        if tf.endswith(".mat"):
            tf_name = f"transform_{fixed_name}.mat"        # 仿射轉換矩陣
        elif tf.endswith(".nii.gz"):
            tf_name = f"transform_{fixed_name}.nii.gz"     # 非線性位移場
        else:
            continue
        tf_out_path = os.path.join(output_dir, tf_name)
        shutil.copy(tf, tf_out_path)

    print(f"  → 已輸出：{warped_image_path}")


if __name__ == "__main__":

    # ===== 可自行修改的參數 =====
    fixed_folder = "腦室分割後 CT 影像的資料夾"  
    moving_img = "CT_template2.nii.gz"          # CT 標準空間模板
    output_folder = "建立輸出資料夾"         # 輸出資料夾

    start_time = time.time()

    # 掃描 fixed_folder 底下所有 .nii.gz 影像（每一個代表一個個體案例）
    fixed_files = [f for f in os.listdir(fixed_folder) if f.endswith(".nii.gz")]

    for fixed_file in fixed_files:
        fixed_path = os.path.join(fixed_folder, fixed_file)
        print(f"Processing {fixed_file}...")
        ants_syn_registration(
            fixed_path=fixed_path,
            moving_path=moving_img,
            output_dir=output_folder,
            transform_type='SyN'
        )

    end_time = time.time()
    print(f"Total registration time: {end_time - start_time:.2f} seconds")