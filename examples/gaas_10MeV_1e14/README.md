# GaAs + cover glass 100 µm, 10 MeV proton, Fluence = 1e14 cm⁻²

この例では、GaAs太陽電池にカバーガラス（100 µm）を付けた構造に対して、10 MeV陽子線を総フルエンス1e14 cm⁻²照射した場合の欠陥数密度を計算する手順を示します。

## 解析手順

### 1. PHITSの実行

PHITSで`[T-DPA]`（NRT+ARC）と`[T-DDD]`タリーを実行し、GaAs層（cell=102）の結果を取得します。

**必要な出力ファイル**:
- `dpa_layers_nrt.out`: NRT-DPA（per-source値）
- `dpa_layers_arc.out`: ARC-DPA（per-source値）
- `ddd_layers.out`: DDD（per-source値）

### 2. per-source出力の取得

PHITS出力ファイルから、GaAs層（cell=102）のper-source値を読み取ります。

**出力形式の例**（2列形式を想定）:
```
102  1.234e-24    # cell_id, DPA_per_source
```

### 3. 総フルエンスでの規格化

per-source値を総フルエンス（1e14 cm⁻²）で規格化します：

```
DPA_mission = DPA_per_source × 1e14
DDD_mission = DDD_per_source × 1e14
```

### 4. 欠陥数密度の計算

#### 推奨方法: DPAから計算（厳密）

DPAから欠陥数密度を計算します：

```
n_defects = DPA_mission × n_atoms
```

**GaAsのパラメータ**:
- 密度: ρ = 5.32 g/cm³
- モル質量: M = 144.64 g/mol（Ga: 69.72, As: 74.92）
- 化学式あたりの原子数: 2（GaAs）

**原子数密度の計算**:
```
n_atoms = (5.32 / 144.64) × 6.022×10²³ × 2 ≈ 4.43×10²² [atoms/cm³]
```

**スクリプトでの実行例**:
```bash
python scripts/defect_density.py \
  --mode dpa \
  --input dpa_layers_nrt.out \
  --fluence 1e14 \
  --cells 102 \
  --rho 5.32 --M 144.64 --atoms_per_formula 2 \
  --csv_out defects_gaas_dpa.csv
```

#### 代替方法: DDDから計算（近似）

DPAが利用できない場合の近似計算：

```
n_defects = η × (DDD_mission[J/g] × ρ[g/cm³]) / (2Ed[J])
```

**パラメータ**:
- Ed ≈ 21–22 eV（Ga/As、SR-NIEL/DLTS相関から推定）
- η = 0.8（NRTモデル、ARCではさらに低下）

**スクリプトでの実行例**:
```bash
python scripts/defect_density.py \
  --mode ddd \
  --input ddd_layers.out \
  --fluence 1e14 \
  --cells 102 \
  --rho 5.32 --Ed 21.5 --eta 0.8 \
  --csv_out defects_gaas_ddd.csv
```

**注意**: DDDからの換算は近似であり、DPAが利用可能な場合はDPAを優先してください。

### 5. SR-NIELによるクロスチェック

SR-NIEL計算機を使用して、GaAsに対するNIEL(E)を取得し、遮蔽後スペクトルで積分してDDDを作成します。

**手順**:
1. SR-NIEL計算機でGaAsのNIEL(E)を取得
2. 遮蔽後スペクトル（カバーガラス100 µm通過後）で積分
3. PHITSの`ddd_layers.out`から得たDDD_missionと比較

**期待される一致度**:
- 通常、数10%以内の一致が期待されます
- 一致しない場合は、Edやhadronic寄与の設定を見直してください

**推奨Ed値**:
- GaAs: Ga/As ≈ 21–22 eV（SR-NIEL/DLTS相関から推定）

## 期待値の例

**10 MeV陽子、フルエンス1e14 cm⁻²の場合**（参考値）:

| パラメータ | NRT-DPA | ARC-DPA | DDD |
|-----------|---------|---------|-----|
| per-source値 | ~1e-24 | ~0.8e-24 | ~0.1 MeV/g |
| mission値 | ~1e-10 | ~0.8e-10 | ~1e10 MeV/g |
| 欠陥数密度 | ~4.4e12 cm⁻³ | ~3.5e12 cm⁻³ | ~4e12 cm⁻³（近似） |

**注意**: 上記の値は参考値です。実際の値は、PHITSの計算結果に基づいてください。

## 参考文献

- **PHITS Manual** (per-source tallies; DPA/DDD sections)  
  https://phits.jaea.go.jp/manual/manualE-phits.pdf

- **NRT vs ARC-DPA in PHITS; validation studies**  
  http://www.aesj.or.jp/~ndd/ndnews/pdf136/No136-02.pdf  
  https://indico.cern.ch/event/1450988/contributions/6259665/attachments/2997259/5280748/RADSUM-iwamoto3.pdf

- **DDD methodology (NRL-DDD; SPENVIS implementation)**  
  https://ntrs.nasa.gov/api/citations/20090022289/downloads/20090022289.pdf

- **SR-NIEL計算機**  
  https://srniel.esa.int/

