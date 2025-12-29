#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GlobalBuildingAtlasからFijiの建物ポリゴンデータを抽出するスクリプト

使用方法:
    python extract_fiji_buildings.py --method wfs --output fiji_buildings.geojson
    python extract_fiji_buildings.py --method download --input path/to/data --output fiji_buildings.geojson
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Tuple

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box, Point

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Fijiのバウンディングボックス
# 緯度: 約 -20.0 ～ -15.0
# 経度: 約 177.0 ～ 180.0 および -180.0 ～ -178.0（日付変更線を跨ぐ）
FIJI_BBOX = {
    'min_lat': -20.0,
    'max_lat': -15.0,
    'min_lon': 177.0,
    'max_lon': 180.0,
    'min_lon_west': -180.0,
    'max_lon_west': -178.0
}

# WFSサービスURL
WFS_URL = "https://tubvsig-so2sat-vm1.srv.mwn.de/geoserver/ows?"


def get_fiji_bbox() -> Tuple[float, float, float, float]:
    """
    Fijiのバウンディングボックスを取得
    日付変更線を跨ぐため、2つのボックスを返す
    
    Returns:
        Tuple: (min_lon, min_lat, max_lon, max_lat) のタプル
    """
    # 東側のボックス
    bbox_east = (FIJI_BBOX['min_lon'], FIJI_BBOX['min_lat'], 
                 FIJI_BBOX['max_lon'], FIJI_BBOX['max_lat'])
    # 西側のボックス
    bbox_west = (FIJI_BBOX['min_lon_west'], FIJI_BBOX['min_lat'],
                 FIJI_BBOX['max_lon_west'], FIJI_BBOX['max_lat'])
    
    return bbox_east, bbox_west


def filter_fiji_buildings(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    GeoDataFrameからFiji地域の建物をフィルタリング
    
    Args:
        gdf: 建物ポリゴンのGeoDataFrame
        
    Returns:
        Fiji地域の建物のみを含むGeoDataFrame
    """
    logger.info(f"フィルタリング前の建物数: {len(gdf)}")
    
    # Fijiのバウンディングボックスを作成
    bbox_east, bbox_west = get_fiji_bbox()
    box_east = box(*bbox_east)
    box_west = box(*bbox_west)
    
    # バウンディングボックス内の建物をフィルタリング
    mask_east = gdf.geometry.intersects(box_east)
    mask_west = gdf.geometry.intersects(box_west)
    mask = mask_east | mask_west
    
    filtered_gdf = gdf[mask].copy()
    
    logger.info(f"フィルタリング後の建物数: {len(filtered_gdf)}")
    
    return filtered_gdf


def get_wfs_layers() -> list:
    """
    WFSサービスから利用可能なレイヤー一覧を取得
    
    Returns:
        レイヤー名のリスト
    """
    try:
        params = {
            'service': 'WFS',
            'version': '2.0.0',
            'request': 'GetCapabilities'
        }
        response = requests.get(WFS_URL, params=params, timeout=30)
        response.raise_for_status()
        
        # XMLをパースしてレイヤー名を抽出
        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.content)
        
        layers = []
        # 名前空間を使用してFeatureTypeを検索
        for feature_type in root.findall('.//{http://www.opengis.net/wfs/2.0}FeatureType'):
            name_elem = feature_type.find('{http://www.opengis.net/wfs/2.0}Name')
            if name_elem is not None and name_elem.text:
                layers.append(name_elem.text)
        
        return layers
    except Exception as e:
        logger.warning(f"WFSレイヤー一覧の取得に失敗: {e}")
        return []


def download_from_wfs(output_path: Path, layer_name: Optional[str] = None) -> gpd.GeoDataFrame:
    """
    WFSサービスからFijiの建物データをダウンロード
    
    Args:
        output_path: 出力ファイルのパス
        layer_name: レイヤー名（Noneの場合は自動検出）
        
    Returns:
        建物ポリゴンのGeoDataFrame
    """
    logger.info("WFSサービスからデータを取得中...")
    
    # レイヤー名が指定されていない場合、利用可能なレイヤーを取得
    if layer_name is None:
        layers = get_wfs_layers()
        if not layers:
            raise ValueError("WFSサービスからレイヤー一覧を取得できませんでした")
        
        # 建物関連のレイヤーを探す
        building_layers = [l for l in layers if 'building' in l.lower() or 'lod' in l.lower()]
        if building_layers:
            layer_name = building_layers[0]
            logger.info(f"レイヤー '{layer_name}' を使用します")
        else:
            layer_name = layers[0]
            logger.info(f"レイヤー '{layer_name}' を使用します（建物レイヤーが見つかりませんでした）")
    
    # Fijiのバウンディングボックスを取得
    bbox_east, bbox_west = get_fiji_bbox()
    
    # 東側と西側のデータを別々に取得
    gdfs = []
    
    for bbox, region in [(bbox_east, 'east'), (bbox_west, 'west')]:
        logger.info(f"Fiji {region}側のデータを取得中...")
        logger.info(f"  バウンディングボックス: {bbox}")
        
        # WFS 2.0のbbox形式: minx,miny,maxx,maxy,CRS
        # CRSはEPSG:4326を指定
        
        # バウンディングボックスを分割して取得（WFSサービスがページネーションをサポートしていないため）
        # 100,000件の制限を回避するために、バウンディングボックスを小さく分割
        min_lon, min_lat, max_lon, max_lat = bbox
        
        # Suva地域を優先的に小さく分割（経度178.3-178.5、緯度-18.2～-18.0）
        # まず、Suva地域を含む小さな領域を取得
        sub_bboxes = []
        
        # Suva地域を優先的に細かく分割
        if region == 'east' and min_lon <= 178.5 and max_lon >= 178.3 and min_lat <= -18.0 and max_lat >= -18.2:
            # Suva地域を4分割
            suva_lons = [178.3, 178.4, 178.5]
            suva_lats = [-18.2, -18.1, -18.0]
            for i in range(len(suva_lons) - 1):
                for j in range(len(suva_lats) - 1):
                    sub_bboxes.append((suva_lons[i], suva_lats[j], suva_lons[i+1], suva_lats[j+1]))
        
        # 残りの領域を分割（Suva地域を除く）
        # 経度方向に2分割、緯度方向に2分割
        lon_step = (max_lon - min_lon) / 2
        lat_step = (max_lat - min_lat) / 2
        
        for i in range(2):
            for j in range(2):
                sub_min_lon = min_lon + i * lon_step
                sub_max_lon = min_lon + (i + 1) * lon_step if i < 1 else max_lon
                sub_min_lat = min_lat + j * lat_step
                sub_max_lat = min_lat + (j + 1) * lat_step if j < 1 else max_lat
                
                # Suva地域のサブボックスと重複しない場合のみ追加
                is_suva_subbox = False
                if region == 'east':
                    for suva_bbox in sub_bboxes:
                        if (sub_min_lon >= suva_bbox[0] and sub_max_lon <= suva_bbox[2] and
                            sub_min_lat >= suva_bbox[1] and sub_max_lat <= suva_bbox[3]):
                            is_suva_subbox = True
                            break
                
                if not is_suva_subbox:
                    sub_bboxes.append((sub_min_lon, sub_min_lat, sub_max_lon, sub_max_lat))
        
        # 各サブボックスからデータを取得
        all_features = []
        total_matched = None
        
        try:
            for idx, sub_bbox in enumerate(sub_bboxes):
                bbox_str = ','.join(map(str, sub_bbox)) + ',EPSG:4326'
                
                params = {
                    'service': 'WFS',
                    'version': '2.0.0',
                    'request': 'GetFeature',
                    'typeName': layer_name,
                    'bbox': bbox_str,
                    'outputFormat': 'application/json',
                    'srsName': 'EPSG:4326'
                }
                
                logger.info(f"  サブボックス {idx+1}/{len(sub_bboxes)}: {sub_bbox}")
                
                response = requests.get(WFS_URL, params=params, timeout=300)
                response.raise_for_status()
                
                # JSONとしてパース
                data = json.loads(response.text)
                
                if 'features' in data:
                    features = data['features']
                    all_features.extend(features)
                    
                    if 'numberMatched' in data and total_matched is None:
                        total_matched = data['numberMatched']
                    
                    logger.info(f"    取得: {len(features)}件（累計: {len(all_features)}件）")
                    
                    # 100,000件に達した場合、さらに細かく分割する必要がある
                    if len(features) == 100000:
                        logger.warning(f"    ⚠️ サブボックスが100,000件の制限に達しています。さらに分割が必要です。")
                else:
                    logger.warning(f"  GeoJSONに'features'キーがありません: {list(data.keys())}")
            
            if not all_features:
                logger.warning(f"Fiji {region}側: データを取得できませんでした")
                continue
            
            # すべてのfeaturesを結合してGeoJSONを作成
            geojson_data = {
                'type': 'FeatureCollection',
                'features': all_features
            }
            
            # GeoJSONを一時ファイルに保存
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False, encoding='utf-8') as f:
                json.dump(geojson_data, f)
                temp_path = f.name
            
            # GeoDataFrameとして読み込み
            gdf = gpd.read_file(temp_path)
            
            gdfs.append(gdf)
            
            # 一時ファイルを削除
            Path(temp_path).unlink()
            
            logger.info(f"Fiji {region}側: {len(gdf)}件の建物を取得（バウンディングボックス分割使用）")
            
        except Exception as e:
            logger.warning(f"Fiji {region}側のデータ取得に失敗: {e}", exc_info=True)
            continue
    
    if not gdfs:
        raise ValueError("WFSサービスからデータを取得できませんでした")
    
    # データを結合
    combined_gdf = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True))
    
    # Fiji地域でフィルタリング（念のため）
    filtered_gdf = filter_fiji_buildings(combined_gdf)
    
    return filtered_gdf


def process_downloaded_data(input_path: Path) -> gpd.GeoDataFrame:
    """
    ダウンロード済みのデータファイルを処理
    
    Args:
        input_path: 入力ファイルまたはディレクトリのパス
        
    Returns:
        建物ポリゴンのGeoDataFrame
    """
    input_path = Path(input_path)
    
    if input_path.is_file():
        # 単一ファイルの場合
        logger.info(f"ファイルを読み込み中: {input_path}")
        gdf = gpd.read_file(input_path)
    elif input_path.is_dir():
        # ディレクトリの場合、GeoJSONファイルを検索
        geojson_files = list(input_path.glob("*.geojson"))
        if not geojson_files:
            raise ValueError(f"ディレクトリ内にGeoJSONファイルが見つかりません: {input_path}")
        
        logger.info(f"{len(geojson_files)}個のGeoJSONファイルを読み込み中...")
        gdfs = []
        for file_path in geojson_files:
            try:
                gdf = gpd.read_file(file_path)
                gdfs.append(gdf)
                logger.info(f"  - {file_path.name}: {len(gdf)}件")
            except Exception as e:
                logger.warning(f"  - {file_path.name}の読み込みに失敗: {e}")
        
        if not gdfs:
            raise ValueError("読み込めるGeoJSONファイルがありませんでした")
        
        gdf = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True))
    else:
        raise ValueError(f"入力パスが無効です: {input_path}")
    
    # Fiji地域でフィルタリング
    filtered_gdf = filter_fiji_buildings(gdf)
    
    return filtered_gdf


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='GlobalBuildingAtlasからFijiの建物ポリゴンデータを抽出'
    )
    parser.add_argument(
        '--method',
        choices=['wfs', 'download'],
        default='wfs',
        help='データ取得方法: wfs (WFSサービス) または download (ダウンロード済みデータ)'
    )
    parser.add_argument(
        '--input',
        type=str,
        help='ダウンロード済みデータのパス（method=downloadの場合に必須）'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='fiji_buildings.geojson',
        help='出力GeoJSONファイルのパス（デフォルト: fiji_buildings.geojson）'
    )
    parser.add_argument(
        '--layer',
        type=str,
        help='WFSレイヤー名（method=wfsの場合、指定しない場合は自動検出）'
    )
    
    args = parser.parse_args()
    
    try:
        if args.method == 'wfs':
            # WFSサービスから取得
            gdf = download_from_wfs(Path(args.output), args.layer)
        else:
            # ダウンロード済みデータを処理
            if not args.input:
                parser.error("--method=download の場合、--input オプションが必要です")
            gdf = process_downloaded_data(Path(args.input))
        
        # GeoJSONとして保存
        output_path = Path(args.output)
        logger.info(f"データを保存中: {output_path}")
        gdf.to_file(output_path, driver='GeoJSON')
        
        logger.info(f"完了: {len(gdf)}件の建物ポリゴンを {output_path} に保存しました")
        
        # 統計情報を表示
        logger.info(f"座標系: {gdf.crs}")
        logger.info(f"カラム: {list(gdf.columns)}")
        if 'geometry' in gdf.columns:
            bounds = gdf.total_bounds
            logger.info(f"バウンディングボックス: "
                       f"({bounds[0]:.6f}, {bounds[1]:.6f}, {bounds[2]:.6f}, {bounds[3]:.6f})")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

