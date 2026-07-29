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

    print(f"Consolidated Pipeline: Processing 100% of national data from {len(active_files)} primary dataset files...")
    import gc
    from collections import defaultdict

    required_cols = [
        'estado_predio_capturada', 'superficie_apoyada',
        'ton_dap_entregada', 'dap_25_kg_anio_actual', 'dap_remanente_25_kg',
        'ton_urea_entregada', 'urea_25_kg_anio_actual', 'urea_remanente_25_kg',
        'curp_renapo', 'curp_solicitud', 'cultivo', 'fecha_entrega',
        'id_nu_solicitud', 'cdf_entrega'
    ]

    state_accum = defaultdict(lambda: {
        'atendidos': 0,
        'dap_sum': 0.0,
        'urea_sum': 0.0,
        'sup_sum': 0.0,
        'hombres': 0,
        'mujeres': 0,
        'ages': defaultdict(int),
        'dates': defaultdict(int),
        'months': defaultdict(int),
        'crops': defaultdict(lambda: {'count': 0, 'sup': 0.0}),
        'cedas': defaultdict(lambda: defaultdict(int))
    })

    total_records_processed = 0

    for f in active_files:
        print(f"Streaming dataset in 50k chunks: {os.path.basename(f)}...")
        header = pd.read_csv(f, encoding='utf-8-sig', nrows=0)
        col_map = {c: c.strip().lower() for c in header.columns}
        cols_to_use = [orig for orig, clean in col_map.items() if clean in required_cols]
        
        for df_sub in pd.read_csv(f, encoding='utf-8-sig', usecols=cols_to_use, chunksize=50000, low_memory=False):
            df_sub.columns = [c.strip().lower() for c in df_sub.columns]
            
            if 'estado_predio_capturada' not in df_sub.columns:
                continue

            df_sub['estado_clean'] = df_sub['estado_predio_capturada'].apply(clean_state_name)
            total_records_processed += len(df_sub)

            if 'superficie_apoyada' in df_sub.columns:
                df_sub['superficie_apoyada'] = pd.to_numeric(df_sub['superficie_apoyada'], errors='coerce').fillna(0.0)
                mask_1ha = df_sub['estado_clean'].isin(['CHIAPAS', 'OAXACA'])
                df_sub.loc[mask_1ha, 'superficie_apoyada'] = np.minimum(df_sub.loc[mask_1ha, 'superficie_apoyada'], 1.0)
            else:
                df_sub['superficie_apoyada'] = 0.0

            dap_ton = pd.to_numeric(df_sub['ton_dap_entregada'], errors='coerce').fillna(0.0) if 'ton_dap_entregada' in df_sub.columns else 0.0
            dap_b25 = pd.to_numeric(df_sub['dap_25_kg_anio_actual'], errors='coerce').fillna(0.0) if 'dap_25_kg_anio_actual' in df_sub.columns else 0.0
            dap_rem = pd.to_numeric(df_sub['dap_remanente_25_kg'], errors='coerce').fillna(0.0) if 'dap_remanente_25_kg' in df_sub.columns else 0.0
            df_sub['dap_total_row'] = np.maximum(dap_ton, (dap_b25 + dap_rem) * 25.0 / 1000.0)

            urea_ton = pd.to_numeric(df_sub['ton_urea_entregada'], errors='coerce').fillna(0.0) if 'ton_urea_entregada' in df_sub.columns else 0.0
            urea_b25 = pd.to_numeric(df_sub['urea_25_kg_anio_actual'], errors='coerce').fillna(0.0) if 'urea_25_kg_anio_actual' in df_sub.columns else 0.0
            urea_rem = pd.to_numeric(df_sub['urea_remanente_25_kg'], errors='coerce').fillna(0.0) if 'urea_remanente_25_kg' in df_sub.columns else 0.0
            df_sub['urea_total_row'] = np.maximum(urea_ton, (urea_b25 + urea_rem) * 25.0 / 1000.0)

            if 'fecha_entrega' in df_sub.columns:
                df_sub['fecha_str'] = df_sub['fecha_entrega'].astype(str).str.slice(0, 10)
            else:
                df_sub['fecha_str'] = ''

            curp_col = 'curp_renapo' if 'curp_renapo' in df_sub.columns else ('curp_solicitud' if 'curp_solicitud' in df_sub.columns else None)
            df_sub['curp_val'] = df_sub[curp_col].astype(str) if curp_col else ''
            if 'cultivo' in df_sub.columns:
                df_sub['cultivo_clean'] = df_sub['cultivo'].apply(clean_crop_name)
            else:
                df_sub['cultivo_clean'] = ''
            ceda_col = 'cdf_entrega' if 'cdf_entrega' in df_sub.columns else None
            df_sub['ceda_val'] = df_sub[ceda_col].astype(str) if ceda_col else ''

            for state_key, group in df_sub.groupby('estado_clean'):
                acc = state_accum[state_key]
                nat = state_accum['NACIONAL']
                cnt = len(group)
                dap_s = float(group['dap_total_row'].sum())
                urea_s = float(group['urea_total_row'].sum())
                sup_s = float(group['superficie_apoyada'].sum())
                acc['atendidos'] += cnt
                acc['dap_sum'] += dap_s
                acc['urea_sum'] += urea_s
                acc['sup_sum'] += sup_s
                nat['atendidos'] += cnt
                nat['dap_sum'] += dap_s
                nat['urea_sum'] += urea_s
                nat['sup_sum'] += sup_s

                c_ser = group['curp_val'].str.strip().str.upper()
                c_valid = c_ser[c_ser.str.len() == 18]
                if not c_valid.empty:
                    g = c_valid.str[10]
                    h_cnt = int((g == 'H').sum())
                    m_cnt = int((g == 'M').sum())
                    acc['hombres'] += h_cnt
                    acc['mujeres'] += m_cnt
                    nat['hombres'] += h_cnt
                    nat['mujeres'] += m_cnt

                    yy = pd.to_numeric(c_valid.str[4:6], errors='coerce')
                    years = np.where(yy > 8, 1900 + yy, 2000 + yy)
                    ages = 2026 - years
                    age_cut = pd.cut(ages, bins=[17, 30, 40, 50, 60, 70, 80, 90, 100, 120], labels=['18-30', '31-40', '41-50', '51-60', '61-70', '71-80', '81-90', '91-100', '100-120'], right=True)
                    for age_lbl, a_cnt in age_cut.value_counts().items():
                        acc['ages'][age_lbl] += int(a_cnt)
                        nat['ages'][age_lbl] += int(a_cnt)

                for f_str, f_cnt in group['fecha_str'].value_counts().items():
                    if isinstance(f_str, str) and len(f_str) == 10 and f_str.startswith('202'):
                        acc['dates'][f_str] += int(f_cnt)
                        nat['dates'][f_str] += int(f_cnt)
                        m_idx = f_str[5:7]
                        m_map = {'03': 'mar', '04': 'abr', '05': 'may', '06': 'jun', '07': 'jul'}
                        if m_idx in m_map:
                            m_lbl = m_map[m_idx]
                            acc['months'][m_lbl] += int(f_cnt)
                            nat['months'][m_lbl] += int(f_cnt)

                if 'cultivo_clean' in group.columns:
                    for c_name, c_grp in group.groupby('cultivo_clean'):
                        c_clean = str(c_name).upper()
                        c_cnt = len(c_grp)
                        c_sup = float(c_grp['superficie_apoyada'].sum())
                        acc['crops'][c_clean]['count'] += c_cnt
                        acc['crops'][c_clean]['sup'] += c_sup
                        nat['crops'][c_clean]['count'] += c_cnt
                        nat['crops'][c_clean]['sup'] += c_sup

                if ceda_col:
                    for ceda_name, ceda_grp in group.groupby('ceda_val'):
                        if str(ceda_name).strip() and str(ceda_name).lower() != 'nan':
                            for f_str, f_cnt in ceda_grp['fecha_str'].value_counts().items():
                                if isinstance(f_str, str) and len(f_str) == 10 and f_str.startswith('202'):
                                    m_idx = f_str[5:7]
                                    m_map = {'03': 'mar', '04': 'abr', '05': 'may', '06': 'jun', '07': 'jul'}
                                    if m_idx in m_map:
                                        acc['cedas'][str(ceda_name)][m_map[m_idx]] += int(f_cnt)

            del df_sub
            gc.collect()

    print(f"Successfully processed {total_records_processed:,} total beneficiary records in zero-list ultra-low RAM mode!")
    data_by_state = {}
    for state_key, acc in state_accum.items():
        if state_key == 'NACIONAL': continue
        atendidos_total = acc['atendidos']
        dap_entregada = acc['dap_sum']
        urea_entregada = acc['urea_sum']
        sup_atendida = acc['sup_sum']
        meta_row = df_meta[df_meta['Estado_Clean'] == state_key]
        if not meta_row.empty:
            r = meta_row.iloc[0]
            prod_meta, sup_meta, dap_meta, urea_meta = int(r['Productores']), float(r['Superficie']), float(r['DAP (ton)']), float(r['UREA (ton)'])
        else:
            prod_meta, sup_meta, dap_meta, urea_meta = atendidos_total, sup_atendida, dap_entregada, urea_entregada
        pct_derechohabientes = round((100.0 / prod_meta * atendidos_total), 2) if prod_meta > 0 else 0.0
        pct_dap = round((100.0 / dap_meta * dap_entregada), 2) if dap_meta > 0 else 0.0
        pct_urea = round((100.0 / urea_meta * urea_entregada), 2) if urea_meta > 0 else 0.0
        pct_ha = round((100.0 / sup_meta * sup_atendida), 2) if sup_meta > 0 else 0.0

        gender_data = {'hombres': acc['hombres'], 'mujeres': acc['mujeres']}
        age_counts = {k: int(acc['ages'].get(k, 0)) for k in ['18-30', '31-40', '41-50', '51-60', '61-70', '71-80', '81-90', '91-100', '100-120']}

        cultivos_list = [{'cultivo': c_name, 'derechohabientes': c_data['count'], 'superficie': round(c_data['sup'], 1), 'porcentaje': f"{(100.0 * c_data['sup'] / sup_atendida if sup_atendida > 0 else 0.0):.4f}%"} for c_name, c_data in sorted(acc['crops'].items(), key=lambda x: x[1]['sup'], reverse=True)]
        entregas_mes = [{'mes': m.upper(), 'conteo': int(acc['months'].get(m, 0))} for m in ['mar', 'abr', 'may', 'jun', 'jul']]
        entregas_by_ceda = [{'ceda': ceda_name, 'puntos': [{'mes': m, 'conteo': int(c_counts.get(m, 0))} for m in ['mar', 'abr', 'may', 'jun', 'jul']]} for ceda_name, c_counts in acc['cedas'].items() if sum(int(c_counts.get(m, 0)) for m in ['mar', 'abr', 'may', 'jun', 'jul']) > 0]
        data_by_state[state_key] = {
            'meta': {'productores': prod_meta, 'urea_ton': round(urea_meta, 3), 'dap_ton': round(dap_meta, 3), 'hectareas': round(sup_meta, 1)},
            'avance': {'atendidos': atendidos_total, 'pct_derechohabientes': pct_derechohabientes, 'dap_entregada': round(dap_entregada, 3), 'pct_dap': pct_dap, 'urea_entregada': round(urea_entregada, 3), 'pct_urea': pct_urea, 'ha_atendidas': round(sup_atendida, 1), 'pct_ha': pct_ha},
            'atenciones_por_fecha': dict(acc['dates']), 'genero': gender_data, 'cultivos': cultivos_list, 'edades': age_counts, 'entregas_mes': entregas_mes, 'entregas_ceda': entregas_by_ceda
        }
    nat_acc = state_accum['NACIONAL']
    nat_atendidos, nat_dap_entregada, nat_urea_entregada, nat_ha_atendidas = nat_acc['atendidos'], nat_acc['dap_sum'], nat_acc['urea_sum'], nat_acc['sup_sum']
    nat_meta_row = df_meta[df_meta['Estado_Clean'] == 'NACIONAL']
    if not nat_meta_row.empty:
        r_nat = nat_meta_row.iloc[0]
        nat_prod_meta, nat_sup_meta, nat_dap_meta, nat_urea_meta = int(r_nat['Productores']), float(r_nat['Superficie']), float(r_nat['DAP (ton)']), float(r_nat['UREA (ton)'])
    else:
        nat_prod_meta, nat_sup_meta, nat_dap_meta, nat_urea_meta = int(df_meta['Productores'].sum()), float(df_meta['Superficie'].sum()), float(df_meta['DAP (ton)'].sum()), float(df_meta['UREA (ton)'].sum())
    nat_gender_data = {'hombres': nat_acc['hombres'], 'mujeres': nat_acc['mujeres']}
    nat_age_counts = {k: int(nat_acc['ages'].get(k, 0)) for k in ['18-30', '31-40', '41-50', '51-60', '61-70', '71-80', '81-90', '91-100', '100-120']}
    nat_cultivos_list = [{'cultivo': c_name, 'derechohabientes': c_data['count'], 'superficie': round(c_data['sup'], 1), 'porcentaje': f"{(100.0 * c_data['sup'] / nat_ha_atendidas if nat_ha_atendidas > 0 else 0.0):.4f}%"} for c_name, c_data in sorted(nat_acc['crops'].items(), key=lambda x: x[1]['sup'], reverse=True)]
    data_by_state['NACIONAL'] = {
        'meta': {'productores': nat_prod_meta, 'urea_ton': round(nat_urea_meta, 3), 'dap_ton': round(nat_dap_meta, 3), 'hectareas': round(nat_sup_meta, 1)},
        'avance': {'atendidos': nat_atendidos, 'pct_derechohabientes': round((100.0 / nat_prod_meta * nat_atendidos), 2) if nat_prod_meta > 0 else 0.0, 'dap_entregada': round(nat_dap_entregada, 3), 'pct_dap': round((100.0 / nat_dap_meta * nat_dap_entregada), 2) if nat_dap_meta > 0 else 0.0, 'urea_entregada': round(nat_urea_entregada, 3), 'pct_urea': round((100.0 / nat_urea_meta * nat_urea_entregada), 2) if nat_urea_meta > 0 else 0.0, 'ha_atendidas': round(nat_ha_atendidas, 1), 'pct_ha': round((100.0 / nat_sup_meta * nat_ha_atendidas), 2) if nat_sup_meta > 0 else 0.0},
        'atenciones_por_fecha': dict(nat_acc['dates']), 'genero': nat_gender_data, 'cultivos': nat_cultivos_list, 'edades': nat_age_counts, 'entregas_mes': [{'mes': m.upper(), 'conteo': int(nat_acc['months'].get(m, 0))} for m in ['mar', 'abr', 'may', 'jun', 'jul']], 'entregas_ceda': []
    }
    print(f"Writing updated JSON dataset to: {OUTPUT_JSON}")
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(data_by_state, f, ensure_ascii=False, indent=2)
    print("Done!")

if __name__ == '__main__':
    process_all_data()
