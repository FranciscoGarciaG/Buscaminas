import os
import re
import datetime
import pandas as pd
import numpy as np
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DBSURI_DIR = os.path.join(BASE_DIR, "DBSURI")
META_PATH = os.path.join(BASE_DIR, "META2026.xlsx")
OUTPUT_JSON = os.path.join(BASE_DIR, "dashboard_data.json")

STATE_NAME_MAPPING = {
    'AGUASCALIENTES': 'AGUASCALIENTES',
    'BAJA CALIFORNIA': 'BAJA CALIFORNIA',
    'BAJA CALIFORNIA SUR': 'BAJA CALIFORNIA SUR',
    'CAMPECHE': 'CAMPECHE',
    'CHIAPAS': 'CHIAPAS',
    'CHIHUAHUA': 'CHIHUAHUA',
    'COAHUILA': 'COAHUILA DE ZARAGOZA',
    'COAHUILA DE ZARAGOZA': 'COAHUILA DE ZARAGOZA',
    'COLIMA': 'COLIMA',
    'DURANGO': 'DURANGO',
    'GUANAJUATO': 'GUANAJUATO',
    'GUERRERO': 'GUERRERO',
    'HIDALGO': 'HIDALGO',
    'JALISCO': 'JALISCO',
    'MEXICO': 'MÉXICO',
    'ESTADO DE MEXICO': 'MÉXICO',
    'ESTADO DE MÉXICO': 'MÉXICO',
    'MÉXICO': 'MÉXICO',
    'MICHOACAN': 'MICHOACÁN',
    'MICHOACAN DE OCAMPO': 'MICHOACÁN',
    'MICHOACÁN': 'MICHOACÁN',
    'MICHOACÁN DE OCAMPO': 'MICHOACÁN',
    'MORELOS': 'MORELOS',
    'NAYARIT': 'NAYARIT',
    'NUEVO LEON': 'NUEVO LEÓN',
    'NUEVO LEÓN': 'NUEVO LEÓN',
    'OAXACA': 'OAXACA',
    'PUEBLA': 'PUEBLA',
    'QUERETARO': 'QUERÉTARO',
    'QUERETARO DE ARTEAGA': 'QUERÉTARO',
    'QUERÉTARO': 'QUERÉTARO',
    'QUINTANA ROO': 'QUINTANA ROO',
    'SAN LUIS POTOSI': 'SAN LUIS POTOSÍ',
    'SAN LUIS POTOSÍ': 'SAN LUIS POTOSÍ',
    'SINALOA': 'SINALOA',
    'SONORA': 'SONORA',
    'TABASCO': 'TABASCO',
    'TAMAULIPAS': 'TAMAULIPAS',
    'TLAXCALA': 'TLAXCALA',
    'VERACRUZ': 'VERACRUZ DE IGNACIO DE LA LLAVE',
    'VERACRUZ DE IGNACIO DE LA LLAVE': 'VERACRUZ DE IGNACIO DE LA LLAVE',
    'YUCATAN': 'YUCATÁN',
    'YUCATÁN': 'YUCATÁN',
    'ZACATECAS': 'ZACATECAS',
    'CIUDAD DE MEXICO': 'CIUDAD DE MÉXICO',
    'CIUDAD DE MÉXICO': 'CIUDAD DE MÉXICO',
    'CDMX': 'CIUDAD DE MÉXICO'
}

def clean_state_name(raw_name):
    if not isinstance(raw_name, str):
        return str(raw_name)
    s = raw_name.strip().upper()
    return STATE_NAME_MAPPING.get(s, s)

def clean_crop_name(raw_crop):
    if not isinstance(raw_crop, str):
        return 'OTRO'
    c = raw_crop.strip().upper()
    c = c.replace('MAÍZ', 'MAIZ')
    
    if 'ELOTERO' in c or 'ELOTE' in c:
        return 'MAIZ ELOTERO'
    if 'MAIZ' in c:
        return 'MAIZ'
    return c

def parse_curp_gender_age(curps):
    curps = curps.dropna().astype(str).str.strip().str.upper()
    curps = curps[curps.str.len() == 18]
    
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

def identify_national_and_sinaloa_csvs():
    os.makedirs(DBSURI_DIR, exist_ok=True)
    raw_files = [os.path.join(DBSURI_DIR, f) for f in os.listdir(DBSURI_DIR) if f.lower().endswith('.csv')]
    
    nac_files = []
    sinaloa_file = None
    
    for f in raw_files:
        fname = os.path.basename(f).upper()
        if 'NACIONAL' in fname:
            nac_files.append(f)
        elif 'SINALOA' in fname:
            sinaloa_file = f
            
    combined = sorted(list(set(nac_files + ([sinaloa_file] if sinaloa_file else []))))
    
    # Fallback: Si los nombres no contienen 'NACIONAL' o 'SINALOA', procesar todos los archivos .csv en DBSURI
    if not combined and raw_files:
        combined = sorted(raw_files)

    return combined

def process_all_data():
    print("Reading META2026.xlsx baseline targets...")
    df_meta = pd.read_excel(META_PATH, sheet_name='META2026')
    df_meta['Estado_Clean'] = df_meta['Estado'].apply(clean_state_name)
    
    active_files = identify_national_and_sinaloa_csvs()
    if not active_files:
        print("No CSV files found in DBSURI. Checking for existing dashboard_data.json...")
        if os.path.exists(OUTPUT_JSON):
            print("Existing dashboard_data.json found. Pipeline completed cleanly.")
            return
        else:
            print("Notice: No CSV files in DBSURI and no existing dashboard_data.json.")
            return

    print(f"Consolidated Pipeline: Processing 100% of national data from {len(active_files)} primary dataset files (6 Cortes Nacionales + Sinaloa)...")
    
    dfs = []
    for f in active_files:
        print(f"Reading dataset: {os.path.basename(f)}...")
        df_sub = pd.read_csv(f, encoding='utf-8-sig', low_memory=False)
        df_sub.columns = [c.strip().lower() for c in df_sub.columns]
        dfs.append(df_sub)
        
    df_all = pd.concat(dfs, ignore_index=True)
    print(f"Successfully loaded {len(df_all):,} total national beneficiary records!")
    
    df_all['estado_clean'] = df_all['estado_predio_capturada'].apply(clean_state_name)
    
    # Rule Adjustment: Cap superficie_apoyada to 1.0 ha per producer for CHIAPAS and OAXACA as requested
    mask_1ha = df_all['estado_clean'].isin(['CHIAPAS', 'OAXACA'])
    if 'superficie_apoyada' in df_all.columns:
        df_all.loc[mask_1ha, 'superficie_apoyada'] = np.minimum(df_all.loc[mask_1ha, 'superficie_apoyada'], 1.0)
    
    data_by_state = {}
    
    # Process each state by grouping the master consolidated dataset
    grouped_states = df_all.groupby('estado_clean')
    
    for state_key, df in grouped_states:
        atendidos_total = len(df)
        
        dap_ton = float(df['ton_dap_entregada'].sum()) if 'ton_dap_entregada' in df.columns else 0.0
        dap_b25 = float(df['dap_25_kg_anio_actual'].sum()) if 'dap_25_kg_anio_actual' in df.columns else 0.0
        dap_rem = float(df['dap_remanente_25_kg'].sum()) if 'dap_remanente_25_kg' in df.columns else 0.0
        dap_entregada = max(dap_ton, (dap_b25 + dap_rem) * 25.0 / 1000.0)
        
        urea_ton = float(df['ton_urea_entregada'].sum()) if 'ton_urea_entregada' in df.columns else 0.0
        urea_b25 = float(df['urea_25_kg_anio_actual'].sum()) if 'urea_25_kg_anio_actual' in df.columns else 0.0
        urea_rem = float(df['urea_remanente_25_kg'].sum()) if 'urea_remanente_25_kg' in df.columns else 0.0
        urea_entregada = max(urea_ton, (urea_b25 + urea_rem) * 25.0 / 1000.0)
        
        sup_atendida = float(df['superficie_apoyada'].sum()) if 'superficie_apoyada' in df.columns else 0.0
        
        meta_row = df_meta[df_meta['Estado_Clean'] == state_key]
        if not meta_row.empty:
            r = meta_row.iloc[0]
            prod_meta = int(r['Productores'])
            sup_meta = float(r['Superficie'])
            dap_meta = float(r['DAP (ton)'])
            urea_meta = float(r['UREA (ton)'])
        else:
            print(f"Notice: State key '{state_key}' not in META2026.xlsx, using actual sum baseline.")
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

    # Now, process NACIONAL from df_all
    nat_atendidos = len(df_all)
    d_ton = float(df_all['ton_dap_entregada'].sum()) if 'ton_dap_entregada' in df_all.columns else 0.0
    d_b25 = float(df_all['dap_25_kg_anio_actual'].sum()) if 'dap_25_kg_anio_actual' in df_all.columns else 0.0
    d_rem = float(df_all['dap_remanente_25_kg'].sum()) if 'dap_remanente_25_kg' in df_all.columns else 0.0
    nat_dap_entregada = max(d_ton, (d_b25 + d_rem) * 25.0 / 1000.0)
    
    u_ton = float(df_all['ton_urea_entregada'].sum()) if 'ton_urea_entregada' in df_all.columns else 0.0
    u_b25 = float(df_all['urea_25_kg_anio_actual'].sum()) if 'urea_25_kg_anio_actual' in df_all.columns else 0.0
    u_rem = float(df_all['urea_remanente_25_kg'].sum()) if 'urea_remanente_25_kg' in df_all.columns else 0.0
    nat_urea_entregada = max(u_ton, (u_b25 + u_rem) * 25.0 / 1000.0)
    
    nat_ha_atendidas = float(df_all['superficie_apoyada'].sum()) if 'superficie_apoyada' in df_all.columns else 0.0
    
    curp_col = 'curp_renapo' if 'curp_renapo' in df_all.columns else ('curp_solicitud' if 'curp_solicitud' in df_all.columns else None)
    if curp_col:
        nat_gender_data, nat_age_counts = parse_curp_gender_age(df_all[curp_col])
    else:
        nat_gender_data = {'hombres': 0, 'mujeres': 0}
        nat_age_counts = {k: 0 for k in ['18-30', '31-40', '41-50', '51-60', '61-70', '71-80', '81-90', '91-100', '100-120']}
        
    df_all['fecha_entrega_dt'] = pd.to_datetime(df_all['fecha_entrega'], errors='coerce')
    df_all['fecha_str'] = df_all['fecha_entrega_dt'].dt.strftime('%Y-%m-%d')
    nat_dates = df_all['fecha_str'].value_counts().to_dict()
    nat_dates = {k: int(v) for k, v in nat_dates.items() if isinstance(k, str) and k != 'NaT'}
    
    nat_cultivos_list = []
    if 'cultivo' in df_all.columns:
        df_all['cultivo_clean'] = df_all['cultivo'].apply(clean_crop_name)
        c_agg = df_all.groupby('cultivo_clean').agg(
            derechohabientes=('id_nu_solicitud', 'count'),
            superficie=('superficie_apoyada', 'sum')
        ).reset_index().sort_values(by='superficie', ascending=False)
        
        for _, cr in c_agg.iterrows():
            sup_val = float(cr['superficie'])
            pct_c = (100.0 * sup_val / nat_ha_atendidas) if nat_ha_atendidas > 0 else 0.0
            nat_cultivos_list.append({
                'cultivo': str(cr['cultivo_clean']).upper(),
                'derechohabientes': int(cr['derechohabientes']),
                'superficie': round(sup_val, 1),
                'porcentaje': f"{pct_c:.4f}%"
            })
            
    df_all['mes_name'] = df_all['fecha_entrega_dt'].dt.strftime('%b').str.lower()
    df_all['mes_name'] = df_all['mes_name'].replace({'apr': 'abr'})
    nat_monthly_counts = df_all['mes_name'].value_counts().to_dict()
    nat_entregas_mes = []
    for m in ['mar', 'abr', 'may', 'jun', 'jul']:
        nat_entregas_mes.append({'mes': m.upper(), 'conteo': int(nat_monthly_counts.get(m, 0))})

    nat_meta_row = df_meta[df_meta['Estado_Clean'] == 'NACIONAL']
    if not nat_meta_row.empty:
        r_nat = nat_meta_row.iloc[0]
        nat_prod_meta = int(r_nat['Productores'])
        nat_sup_meta = float(r_nat['Superficie'])
        nat_dap_meta = float(r_nat['DAP (ton)'])
        nat_urea_meta = float(r_nat['UREA (ton)'])
    else:
        nat_prod_meta = int(df_meta['Productores'].sum())
        nat_sup_meta = float(df_meta['Superficie'].sum())
        nat_dap_meta = float(df_meta['DAP (ton)'].sum())
        nat_urea_meta = float(df_meta['UREA (ton)'].sum())

    pct_derechohabientes_nat = round((100.0 / nat_prod_meta * nat_atendidos), 2) if nat_prod_meta > 0 else 0.0
    pct_dap_nat = round((100.0 / nat_dap_meta * nat_dap_entregada), 2) if nat_dap_meta > 0 else 0.0
    pct_urea_nat = round((100.0 / nat_urea_meta * nat_urea_entregada), 2) if nat_urea_meta > 0 else 0.0
    pct_ha_nat = round((100.0 / nat_sup_meta * nat_ha_atendidas), 2) if nat_sup_meta > 0 else 0.0

    data_by_state['NACIONAL'] = {
        'meta': {
            'productores': nat_prod_meta,
            'urea_ton': round(nat_urea_meta, 3),
            'dap_ton': round(nat_dap_meta, 3),
            'hectareas': round(nat_sup_meta, 1)
        },
        'avance': {
            'atendidos': nat_atendidos,
            'pct_derechohabientes': pct_derechohabientes_nat,
            'dap_entregada': round(nat_dap_entregada, 3),
            'pct_dap': pct_dap_nat,
            'urea_entregada': round(nat_urea_entregada, 3),
            'pct_urea': pct_urea_nat,
            'ha_atendidas': round(nat_ha_atendidas, 1),
            'pct_ha': pct_ha_nat
        },
        'atenciones_por_fecha': nat_dates,
        'genero': nat_gender_data,
        'cultivos': nat_cultivos_list,
        'edades': nat_age_counts,
        'entregas_mes': nat_entregas_mes,
        'entregas_ceda': []
    }

    print(f"Writing updated JSON dataset to: {OUTPUT_JSON}")
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(data_by_state, f, ensure_ascii=False, indent=2)
    print("Done!")

if __name__ == '__main__':
    process_all_data()
