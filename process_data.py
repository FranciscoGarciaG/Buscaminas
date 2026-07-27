import os
import glob
import json
import re
import unicodedata
from datetime import datetime
import pandas as pd
import numpy as np

# Paths
BASE_DIR = r'c:\Users\pacor\Desktop\ESTADISTICO'
META_PATH = os.path.join(BASE_DIR, 'META2026.xlsx')
DBSURI_DIR = os.path.join(BASE_DIR, 'DBSURI')
OUTPUT_JSON = os.path.join(BASE_DIR, 'dashboard_data.json')

def clean_state_name(val):
    if not isinstance(val, str):
        return ''
    s = val.strip().upper()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^A-Z0-9 ]', '', s)
    
    suffixes = [
        ' DE ZARAGOZA',
        ' DE OCAMPO',
        ' DE ARTEAGA',
        ' DE IGNACIO DE LA LLAVE',
        ' DE LA LLAVE',
        ' DE CORONA'
    ]
    for suffix in suffixes:
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
    return s

def clean_crop_name(cname):
    if not isinstance(cname, str):
        return 'OTROS'
    s = cname.strip().upper()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    
    # Merge MAIZ GRANO, MAIZ, MAIZ ELOTERO into MAIZ per user instruction
    if s in ['MAIZ GRANO', 'MAIZ', 'MAIZ ELOTERO']:
        return 'MAIZ'
    return s

def get_file_timestamp(fpath):
    fname = os.path.basename(fpath)
    m = re.search(r'Reporte_SURI_(\d{8}_\d{6})', fname, re.IGNORECASE)
    if m:
        return m.group(1)
    return str(os.path.getmtime(fpath))

def parse_curp_gender_age(curp_series):
    curps = curp_series.astype(str).str.strip().str.upper()
    genders = curps.str[10]
    hombres = int((genders == 'H').sum())
    mujeres = int((genders == 'M').sum())
    
    bins = [17, 30, 40, 50, 60, 70, 80, 90, 100, 120]
    labels = ['18-30', '31-40', '41-50', '51-60', '61-70', '71-80', '81-90', '91-100', '100-120']
    
    yy = pd.to_numeric(curps.str[4:6], errors='coerce')
    years = np.where(yy > 8, 1900 + yy, 2000 + yy)
    ages = 2026 - years
    
    age_cut = pd.cut(ages, bins=bins, labels=labels, right=True)
    age_counts = age_cut.value_counts().reindex(labels, fill_value=0).to_dict()
    age_counts = {k: int(v) for k, v in age_counts.items()}
    
    return {'hombres': hombres, 'mujeres': mujeres}, age_counts

def identify_latest_and_obsolete_csvs():
    raw_files = [os.path.join(DBSURI_DIR, f) for f in os.listdir(DBSURI_DIR) if f.lower().endswith('.csv')]
    csv_files = sorted(list(set(raw_files)))
    
    state_grouped = {}
    nacional_corte_grouped = {}
    
    for f in csv_files:
        fname = os.path.basename(f)
        ts = get_file_timestamp(f)
        fname_upper = fname.upper()
        
        if 'NACIONAL' in fname_upper:
            m = re.search(r'(PRIMER|SEGUNDO|TERCER|CUARTO|QUINTO|SEXTO|SEPTIMO|OCTAVO|NOVENO|DECIMO)\s+CORTE', fname_upper)
            corte_id = m.group(0).strip() if m else fname_upper
            if corte_id not in nacional_corte_grouped:
                nacional_corte_grouped[corte_id] = []
            nacional_corte_grouped[corte_id].append((ts, f))
        else:
            if 'MULTIFERTILIZANTES-' in fname_upper:
                part = fname_upper.split('MULTIFERTILIZANTES-')[1]
                state_key = part.split('-')[0].strip()
            else:
                state_key = fname_upper
                
            state_key = clean_state_name(state_key)
            if state_key not in state_grouped:
                state_grouped[state_key] = []
            state_grouped[state_key].append((ts, f))
        
    picked_states = {}
    obsolete_files = []
    
    for key, flist in state_grouped.items():
        flist.sort(key=lambda x: x[0], reverse=True)
        newest_file = flist[0][1]
        picked_states[key] = newest_file
        
        if len(flist) > 1:
            for old_ts, old_path in flist[1:]:
                if old_path != newest_file and old_path not in obsolete_files:
                    obsolete_files.append(old_path)
        
    picked_nacional = []
    for cid, flist in nacional_corte_grouped.items():
        flist.sort(key=lambda x: x[0], reverse=True)
        newest_file = flist[0][1]
        picked_nacional.append(newest_file)
        
        if len(flist) > 1:
            for old_ts, old_path in flist[1:]:
                if old_path != newest_file and old_path not in obsolete_files:
                    obsolete_files.append(old_path)
        
    return picked_states, picked_nacional, obsolete_files

def process_all_data():
    print("Reading META2026.xlsx...")
    df_meta = pd.read_excel(META_PATH, sheet_name='META2026')
    df_meta['Estado_Clean'] = df_meta['Estado'].apply(clean_state_name)
    
    print("Finding active CSV files in DBSURI...")
    csv_state_map, nacional_corte_files, obsolete_files = identify_latest_and_obsolete_csvs()
    print(f"Active datasets: {len(csv_state_map)} state files and {len(nacional_corte_files)} national corte files.")
    
    data_by_state = {}
    
    nat_meta_row = df_meta[df_meta['Estado_Clean'] == 'NACIONAL']
    if not nat_meta_row.empty:
        r_nat = nat_meta_row.iloc[0]
        nat_meta = {
            'productores': int(r_nat['Productores']),
            'superficie': float(r_nat['Superficie']),
            'dap': float(r_nat['DAP (ton)']),
            'urea': float(r_nat['UREA (ton)'])
        }
    else:
        nat_meta = {
            'productores': int(df_meta['Productores'].sum()),
            'superficie': float(df_meta['Superficie'].sum()),
            'dap': float(df_meta['DAP (ton)'].sum()),
            'urea': float(df_meta['UREA (ton)'].sum())
        }
    
    for state_key, csv_path in csv_state_map.items():
        print(f"Processing state: {state_key} ({os.path.basename(csv_path)})...")
        
        df = pd.read_csv(csv_path, encoding='utf-8-sig', low_memory=False)
        df.columns = [c.strip().lower() for c in df.columns]
        
        atendidos_total = len(df)
        dap_entregada = float(df['ton_dap_entregada'].sum()) if 'ton_dap_entregada' in df.columns else 0.0
        urea_entregada = float(df['ton_urea_entregada'].sum()) if 'ton_urea_entregada' in df.columns else 0.0
        sup_atendida = float(df['superficie_apoyada'].sum()) if 'superficie_apoyada' in df.columns else 0.0
        
        meta_row = df_meta[df_meta['Estado_Clean'] == state_key]
        if not meta_row.empty:
            r = meta_row.iloc[0]
            prod_meta = int(r['Productores'])
            sup_meta = float(r['Superficie'])
            dap_meta = float(r['DAP (ton)'])
            urea_meta = float(r['UREA (ton)'])
        else:
            print(f"Notice: State key '{state_key}' not found in META2026.xlsx, using actual totals as meta baseline.")
            prod_meta = atendidos_total
            sup_meta = sup_atendida
            dap_meta = dap_entregada
            urea_meta = urea_entregada
            
        pct_derechohabientes = round((100.0 / prod_meta * atendidos_total), 2) if prod_meta > 0 else 0.0
        pct_dap = round((100.0 / dap_meta * dap_entregada), 2) if dap_meta > 0 else 0.0
        pct_urea = round((100.0 / urea_meta * urea_entregada), 2) if urea_meta > 0 else 0.0
        pct_ha = round((100.0 / sup_meta * sup_atendida), 2) if sup_meta > 0 else 0.0
        
        df['fecha_entrega_dt'] = pd.to_datetime(df['fecha_entrega'], errors='coerce')
        df['fecha_str'] = df['fecha_entrega_dt'].dt.strftime('%Y-%m-%d')
        atenciones_por_fecha = df['fecha_str'].value_counts().to_dict()
        atenciones_por_fecha = {k: int(v) for k, v in atenciones_por_fecha.items() if isinstance(k, str) and k != 'NaT'}
        
        curp_col = 'curp_renapo' if 'curp_renapo' in df.columns else ('curp_solicitud' if 'curp_solicitud' in df.columns else None)
        if curp_col:
            gender_data, age_counts = parse_curp_gender_age(df[curp_col])
        else:
            gender_data = {'hombres': 0, 'mujeres': 0}
            age_counts = {k: 0 for k in ['18-30', '31-40', '41-50', '51-60', '61-70', '71-80', '81-90', '91-100', '100-120']}
            
        cultivos_list = []
        if 'cultivo' in df.columns:
            df['cultivo_clean'] = df['cultivo'].apply(clean_crop_name)
            cult_agg = df.groupby('cultivo_clean').agg(
                derechohabientes=('id_nu_solicitud', 'count'),
                superficie=('superficie_apoyada', 'sum')
            ).reset_index().sort_values(by='superficie', ascending=False)
            
            for _, cr in cult_agg.iterrows():
                sup_val = float(cr['superficie'])
                pct_c = (100.0 * sup_val / sup_atendida) if sup_atendida > 0 else 0.0
                cultivos_list.append({
                    'cultivo': str(cr['cultivo_clean']).upper(),
                    'derechohabientes': int(cr['derechohabientes']),
                    'superficie': round(sup_val, 1),
                    'porcentaje': f"{pct_c:.4f}%"
                })

        df['mes_name'] = df['fecha_entrega_dt'].dt.strftime('%b').str.lower()
        df['mes_name'] = df['mes_name'].replace({'apr': 'abr'})
        
        monthly_counts = df['mes_name'].value_counts().to_dict()
        entregas_mes = []
        for m in ['mar', 'abr', 'may', 'jun', 'jul']:
            entregas_mes.append({
                'mes': m.upper(),
                'conteo': int(monthly_counts.get(m, 0))
            })
            
        entregas_by_ceda = []
        ceda_col = 'cdf_entrega' if 'cdf_entrega' in df.columns else None
        if ceda_col:
            for ceda_name, cgroup in df.groupby(ceda_col):
                c_counts = cgroup['mes_name'].value_counts().to_dict()
                points = []
                for m in ['mar', 'abr', 'may', 'jun', 'jul']:
                    cnt = int(c_counts.get(m, 0))
                    points.append({'mes': m, 'conteo': cnt})
                
                if sum(p['conteo'] for p in points) > 0:
                    entregas_by_ceda.append({
                        'ceda': str(ceda_name),
                        'puntos': points
                    })
                
        data_by_state[state_key] = {
            'meta': {
                'productores': prod_meta,
                'urea_ton': round(urea_meta, 3),
                'dap_ton': round(dap_meta, 3),
                'hectareas': round(sup_meta, 1)
            },
            'avance': {
                'atendidos': atendidos_total,
                'pct_derechohabientes': pct_derechohabientes,
                'dap_entregada': round(dap_entregada, 3),
                'pct_dap': pct_dap,
                'urea_entregada': round(urea_entregada, 3),
                'pct_urea': pct_urea,
                'ha_atendidas': round(sup_atendida, 1),
                'pct_ha': pct_ha
            },
            'atenciones_por_fecha': atenciones_por_fecha,
            'genero': gender_data,
            'cultivos': cultivos_list,
            'edades': age_counts,
            'entregas_mes': entregas_mes,
            'entregas_ceda': entregas_by_ceda
        }

    print(f"Processing NACIONAL by aggregating {len(nacional_corte_files)} corte files...")
    nat_atendidos = 0
    nat_dap_entregada = 0.0
    nat_urea_entregada = 0.0
    nat_ha_atendidas = 0.0
    nat_hombres = 0
    nat_mujeres = 0
    nat_dates = {}
    nat_edades = {k: 0 for k in ['18-30', '31-40', '41-50', '51-60', '61-70', '71-80', '81-90', '91-100', '100-120']}
    nat_cultivos_map = {}
    nat_monthly_counts = {m: 0 for m in ['mar', 'abr', 'may', 'jun', 'jul']}
    
    for cfile in nacional_corte_files:
        print(f"Reading national corte file: {os.path.basename(cfile)}...")
        df_c = pd.read_csv(cfile, encoding='utf-8-sig', low_memory=False)
        df_c.columns = [c.strip().lower() for c in df_c.columns]
        
        nat_atendidos += len(df_c)
        nat_dap_entregada += float(df_c['ton_dap_entregada'].sum()) if 'ton_dap_entregada' in df_c.columns else 0.0
        nat_urea_entregada += float(df_c['ton_urea_entregada'].sum()) if 'ton_urea_entregada' in df_c.columns else 0.0
        nat_ha_atendidas += float(df_c['superficie_apoyada'].sum()) if 'superficie_apoyada' in df_c.columns else 0.0
        
        curp_col = 'curp_renapo' if 'curp_renapo' in df_c.columns else ('curp_solicitud' if 'curp_solicitud' in df_c.columns else None)
        if curp_col:
            gdata, acounts = parse_curp_gender_age(df_c[curp_col])
            nat_hombres += gdata['hombres']
            nat_mujeres += gdata['mujeres']
            for k, v in acounts.items():
                if k in nat_edades:
                    nat_edades[k] += v
                    
        df_c['fecha_entrega_dt'] = pd.to_datetime(df_c['fecha_entrega'], errors='coerce')
        df_c['fecha_str'] = df_c['fecha_entrega_dt'].dt.strftime('%Y-%m-%d')
        f_counts = df_c['fecha_str'].value_counts().to_dict()
        for d, cnt in f_counts.items():
            if isinstance(d, str) and d != 'NaT':
                nat_dates[d] = nat_dates.get(d, 0) + int(cnt)
                
        if 'cultivo' in df_c.columns:
            df_c['cultivo_clean'] = df_c['cultivo'].apply(clean_crop_name)
            c_agg = df_c.groupby('cultivo_clean').agg(
                derechohabientes=('id_nu_solicitud', 'count'),
                superficie=('superficie_apoyada', 'sum')
            ).reset_index()
            for _, cr in c_agg.iterrows():
                cname = str(cr['cultivo_clean']).upper()
                if cname not in nat_cultivos_map:
                    nat_cultivos_map[cname] = {'derechohabientes': 0, 'superficie': 0.0}
                nat_cultivos_map[cname]['derechohabientes'] += int(cr['derechohabientes'])
                nat_cultivos_map[cname]['superficie'] += float(cr['superficie'])
                
        df_c['mes_name'] = df_c['fecha_entrega_dt'].dt.strftime('%b').str.lower()
        df_c['mes_name'] = df_c['mes_name'].replace({'apr': 'abr'})
        m_counts = df_c['mes_name'].value_counts().to_dict()
        for m, cnt in m_counts.items():
            if m in nat_monthly_counts:
                nat_monthly_counts[m] += int(cnt)

    nat_cultivos_list = []
    for cname, cvals in sorted(nat_cultivos_map.items(), key=lambda x: x[1]['superficie'], reverse=True):
        sup_val = round(cvals['superficie'], 1)
        pct_c = (100.0 * sup_val / nat_ha_atendidas) if nat_ha_atendidas > 0 else 0.0
        nat_cultivos_list.append({
            'cultivo': cname,
            'derechohabientes': cvals['derechohabientes'],
            'superficie': sup_val,
            'porcentaje': f"{pct_c:.4f}%"
        })
        
    nat_entregas_mes = []
    for m in ['mar', 'abr', 'may', 'jun', 'jul']:
        nat_entregas_mes.append({'mes': m.upper(), 'conteo': nat_monthly_counts.get(m, 0)})

    data_by_state['NACIONAL'] = {
        'meta': {
            'productores': nat_meta['productores'],
            'urea_ton': round(nat_meta['urea'], 3),
            'dap_ton': round(nat_meta['dap'], 3),
            'hectareas': round(nat_meta['superficie'], 1)
        },
        'avance': {
            'atendidos': nat_atendidos,
            'pct_derechohabientes': round((100.0 / nat_meta['productores'] * nat_atendidos), 2) if nat_meta['productores'] > 0 else 0.0,
            'dap_entregada': round(nat_dap_entregada, 3),
            'pct_dap': round((100.0 / nat_meta['dap'] * nat_dap_entregada), 2) if nat_meta['dap'] > 0 else 0.0,
            'urea_entregada': round(nat_urea_entregada, 3),
            'pct_urea': round((100.0 / nat_meta['urea'] * nat_urea_entregada), 2) if nat_meta['urea'] > 0 else 0.0,
            'ha_atendidas': round(nat_ha_atendidas, 1),
            'pct_ha': round((100.0 / nat_meta['superficie'] * nat_ha_atendidas), 2) if nat_meta['superficie'] > 0 else 0.0
        },
        'atenciones_por_fecha': nat_dates,
        'genero': {'hombres': nat_hombres, 'mujeres': nat_mujeres},
        'cultivos': nat_cultivos_list,
        'edades': nat_edades,
        'entregas_mes': nat_entregas_mes,
        'entregas_ceda': []
    }
    
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(data_by_state, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully generated dataset at: {OUTPUT_JSON}")
    
    if obsolete_files:
        print(f"Cleaning up {len(obsolete_files)} older obsolete CSV files...")
        for old_path in obsolete_files:
            try:
                if os.path.exists(old_path):
                    os.remove(old_path)
                    print(f"Deleted older version: {os.path.basename(old_path)}")
            except Exception as e:
                print(f"Warning: could not delete {old_path}: {e}")

if __name__ == '__main__':
    process_all_data()
