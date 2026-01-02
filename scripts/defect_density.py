#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
defect_density.py
PHITSのDPA/DDD出力を読み取り、単位体積あたり欠陥数密度 [cm^-3] に換算するスクリプト

参考文献:
- PHITS manual v3.33–3.35 (per-source tally, DPA/DDD) [1]
- NRT/ARC-DPA methodology (Iwamoto et al.) [2][3]
- SR-NIEL & DDD methodology (Summers/Messenger et al.) [4]

[1] https://phits.jaea.go.jp/manual/manualE-phits.pdf
[2] http://www.aesj.or.jp/~ndd/ndnews/pdf136/No136-02.pdf
[3] https://indico.cern.ch/event/1450988/contributions/6259665/attachments/2997259/5280748/RADSUM-iwamoto3.pdf
[4] https://ntrs.nasa.gov/api/citations/20090022289/downloads/20090022289.pdf
"""
import argparse
import csv
import math

# 物理定数
NA = 6.02214076e23       # アボガドロ数 [1/mol]
eV_to_J = 1.602176634e-19  # eV → J 変換係数
MeV_to_J = 1.602176634e-13  # MeV → J 変換係数


def atomic_density(rho_g_cm3, molar_mass_g_mol, atoms_per_formula):
    """
    化合物の原子数密度 [atoms/cm^3] を計算
    
    パラメータ:
        rho_g_cm3: 密度 [g/cm³]
        molar_mass_g_mol: モル質量 [g/mol]
        atoms_per_formula: 化学式あたりの原子数
    
    戻り値:
        原子数密度 [atoms/cm³]
    """
    n_formula = (rho_g_cm3 / molar_mass_g_mol) * NA   # [formula/cm³]
    return n_formula * atoms_per_formula               # [atoms/cm³]


def defects_from_dpa(DPA_mission, n_atoms_cm3):
    """
    DPAから欠陥数密度 [cm^-3] を計算（厳密計算）
    
    パラメータ:
        DPA_mission: ミッションDPA値（総フルエンス規格化済み）
        n_atoms_cm3: 原子数密度 [atoms/cm³]
    
    戻り値:
        欠陥数密度 [defects/cm³]
    """
    return DPA_mission * n_atoms_cm3


def defects_from_ddd(DDD_mission_MeV_g, rho_g_cm3, Ed_eV, eta=0.8):
    """
    DDDから欠陥数密度 [cm^-3] を計算（近似計算）
    
    注意: この方法は近似であり、DPAが利用可能な場合はDPAを優先してください。
    
    パラメータ:
        DDD_mission_MeV_g: ミッションDDD値 [MeV/g]（総フルエンス規格化済み）
        rho_g_cm3: 密度 [g/cm³]
        Ed_eV: はじき出ししきい値 [eV]
        eta: 欠陥生成効率（NRT=0.8、ARCではさらに低下）
    
    戻り値:
        欠陥数密度 [defects/cm³]
    """
    DDD_J_cm3 = DDD_mission_MeV_g * MeV_to_J * rho_g_cm3  # [J/cm³]
    Ed_J = Ed_eV * eV_to_J
    return eta * (DDD_J_cm3 / (2.0 * Ed_J))                # [defects/cm³]


def parse_phits_simple(path):
    """
    PHITS出力ファイルの簡易パーサ
    
    2列形式（cell_id, value_per_source）を想定しています。
    PHITS出力形式が異なる場合は、この関数をカスタマイズしてください。
    
    パラメータ:
        path: PHITS出力ファイルのパス
    
    戻り値:
        {cell_id: value_per_source} の辞書
    """
    out = {}
    with open(path, 'r', encoding='utf-8', newline='') as f:
        for row in csv.reader(f, delimiter=None, skipinitialspace=True):
            if not row or row[0].startswith(('#', '!', 'file')):
                continue
            try:
                cell = int(row[0])
                val = float(row[1])
                out[cell] = val
            except (ValueError, IndexError):
                continue
    return out


def main():
    ap = argparse.ArgumentParser(
        description="PHITS DPA/DDD → 欠陥数密度換算ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # DPAモード（GaAs例）
  python scripts/defect_density.py \\
    --mode dpa \\
    --input dpa_layers.out \\
    --fluence 1e14 \\
    --cells 102 \\
    --rho 5.32 --M 144.64 --atoms_per_formula 2 \\
    --csv_out defects_gaas_dpa.csv
  
  # DDDモード（近似換算）
  python scripts/defect_density.py \\
    --mode ddd \\
    --input ddd_layers.out \\
    --fluence 1e14 \\
    --cells 102 \\
    --rho 5.32 --Ed 21.5 --eta 0.8 \\
    --csv_out defects_gaas_ddd.csv
        """
    )
    
    ap.add_argument("--mode", choices=["dpa", "ddd"], required=True,
                    help="DPAタリー（推奨）またはDDDタリー（近似）を使用")
    ap.add_argument("--input", required=True,
                    help="PHITS出力ファイル（per-source値）")
    ap.add_argument("--fluence", type=float, required=True,
                    help="総フルエンス [cm^-2]")
    ap.add_argument("--cells", nargs="+", type=int, required=True,
                    help="対象セルID（複数指定可能）")
    
    # DPAモード用パラメータ
    ap.add_argument("--rho", type=float,
                    help="密度 [g/cm^3]")
    ap.add_argument("--M", type=float,
                    help="モル質量 [g/mol]")
    ap.add_argument("--atoms_per_formula", type=float,
                    help="化学式あたりの原子数（化合物の場合）")
    
    # DDDモード用パラメータ
    ap.add_argument("--Ed", type=float,
                    help="はじき出ししきい値 [eV]")
    ap.add_argument("--eta", type=float, default=0.8,
                    help="欠陥生成効率（NRT=0.8、ARCではさらに低下、デフォルト: 0.8）")
    
    ap.add_argument("--csv_out", default="defects_out.csv",
                    help="出力CSVファイル名（デフォルト: defects_out.csv）")
    
    args = ap.parse_args()
    
    # PHITS出力ファイルの読み込み
    try:
        data = parse_phits_simple(args.input)
    except FileNotFoundError:
        print(f"[エラー] ファイルが見つかりません: {args.input}")
        return 1
    except Exception as e:
        print(f"[エラー] ファイルの読み込みに失敗しました: {e}")
        return 1
    
    # 結果を格納するリスト
    rows = [("cell", "per_source", "mission_value", "defects_cm3")]
    
    if args.mode == "dpa":
        # DPAモード
        if not (args.rho and args.M and args.atoms_per_formula):
            print("[エラー] DPAモードでは --rho, --M, --atoms_per_formula が必要です")
            return 1
        
        n_atoms = atomic_density(args.rho, args.M, args.atoms_per_formula)
        print(f"[情報] 原子数密度: {n_atoms:.2e} [atoms/cm³]")
        
        for c in args.cells:
            per_src = data.get(c, 0.0)
            mission = per_src * args.fluence
            defects = defects_from_dpa(mission, n_atoms)
            rows.append((c, per_src, mission, defects))
            print(f"[情報] セル {c}: DPA_per_source={per_src:.2e}, "
                  f"DPA_mission={mission:.2e}, "
                  f"欠陥数密度={defects:.2e} [cm⁻³]")
    
    elif args.mode == "ddd":
        # DDDモード
        if not (args.rho and args.Ed):
            print("[エラー] DDDモードでは --rho と --Ed が必要です")
            return 1
        
        print(f"[警告] DDDモードは近似計算です。DPAが利用可能な場合はDPAを優先してください。")
        print(f"[情報] Ed={args.Ed} [eV], η={args.eta}")
        
        for c in args.cells:
            per_src = data.get(c, 0.0)     # [MeV/g per source]
            mission = per_src * args.fluence
            defects = defects_from_ddd(mission, args.rho, args.Ed, args.eta)
            rows.append((c, per_src, mission, defects))
            print(f"[情報] セル {c}: DDD_per_source={per_src:.2e} [MeV/g], "
                  f"DDD_mission={mission:.2e} [MeV/g], "
                  f"欠陥数密度={defects:.2e} [cm⁻³]")
    
    # CSVファイルに出力
    try:
        with open(args.csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerows(rows)
        print(f"[OK] 結果を出力しました: {args.csv_out}")
    except Exception as e:
        print(f"[エラー] CSVファイルの書き込みに失敗しました: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

