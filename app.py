import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import ssl
import xmlrpc.client
import pandas as pd
import plotly.graph_objects as go
import json
import random


ODOO_URL = 'https://quiron.centralus.cloudapp.azure.com/'  # o 'http://localhost:8069'
ODOO_DB = 'quiron_odoo'
ODOO_USERNAME = 'admin'
ODOO_PASSWORD = 'admin'

# Diccionario para abreviaciones en español
meses_es = {
    1: "Ene",
    2: "Feb",
    3: "Mar",
    4: "Abr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dic"
}

# Diccionario de mapeo: Texto mostrado -> Valor real
type_map = {
    "Asignación": "asignacion",
    "Programación": "programacion",
    "Ejecución": "ejecucion",
    "Soportes": "soportes",
    "Facturación": "facturacion"
}


# Desactivamos la verificación SSL sólo si es necesario
ssl_context = ssl._create_unverified_context()


import pandas as pd
import json
import random

def get_api_data(start_date, end_date, selected_type):
    # 1. Cargar el JSON local
    with open("data.json", "r", encoding="utf-8") as f:
        data_list = json.load(f)

    # 2. Crear DataFrame
    df = pd.DataFrame(data_list)

    # 3. Convertir 'date' a datetime y normalizar
    df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.normalize()

    # 4. Filtrar rango de fechas
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]

    # 5. Filtrar por tipo
    df = df[df['type'] == selected_type]

    # 6. Omitir ciertos ejecutores
    excluded_executors = [
        "ACOSTA LEGUIZAMO MYRIAM SOFIA",
        "LISCANO RAMIREZ ADRIANA LORENA",
        "MESES APARICIO LEIDY JUDITH",
        "MU\u00d1OZ RUIZ NURY TATIANA"
    ]
    df = df[~df['executor'].isin(excluded_executors)]

    # 🎩 Truquillo: Si order_name empieza con "PS", cámbialo a "QPPS"
    df['order_name'] = df['order_name'].apply(lambda x: f"QPPS{x[2:]}" if x.startswith("PS") else x)

    # 🎩 Truquillo extra: Si el tipo es 'ejecucion', agrega un campo 'activity' con un valor aleatorio
    if selected_type == "ejecucion":
        activities = [
            "Asesoría al SVE psicosocial",
            "Capacitación en comunicación asertiva",
            "Capacitación en estilos de vida saludable",
            "Asesoría al protocolo del comité de convivencia laboral"
        ]
        df['activity'] = df.apply(lambda _: random.choice(activities), axis=1)

    return df


tabs = st.tabs(["Indicadores de área","Indicadores por Psicólogo", "Indicadores por Empresa", "Indicadores por Cliente"])


# Diccionario con códigos QPPS y su detalle
QPPS_CODES = {
    "QPPS-1001-RME": ("DESARROLLO Y TRANSFORMACIÓN DE EQUIPO", "REUNIONES MENSUALES DE EQUIPO", "ESTE CÓDIGO SE UTILIZARÁ PARA REPORTAR LAS HORAS EFECTIVAS DE CADA REUNIÓN MENSUAL DE EQUIPO QUE SE REALICE.", "NO"),
    "QPPS-1002-RI": ("DESARROLLO Y TRANSFORMACIÓN DE EQUIPO", "REUNIONES INDIVIDUALES", "ESTE CÓDIGO SE UTILIZARÁ PARA REPORTAR LAS HORAS EFECTIVAS DE LAS REUNIONES QUE SE REALICEN CON LOS LÍDERES DEL ÁREA Y QUE SUPERE 1 HORA LA REUNIÓN", "NO"),
    "QPPS-1003-CV": ("SERVICIO AL CLIENTE INTERNO", "CAFES VIRTUALES", "ESTE CÓDIGO SE UTILIZARÁ PARA REPORTAR LAS HORAS EFECTIVAS ÚNICAMENTE CUANDO LOS PROFESIONALES DEL ÁREA PARTICIPEN DE MANERA ACTIVA EN LOS CAFES MENSUALES", "SI"),
    "QPPS-1004-DMI": ("DISEÑO DE PRODUCTOS", "DESARROLLO DE MATERIAL INTERNO Y DISEÑO DE PRODUCTOS", "ESTE CÓDIGO SE UTILIZARÁ PARA REPORTAR LAS HORAS EFECTIVAS RELACIONADAS AL DISEÑO Y/O REALIZACIÓN DE MATERIAL NUEVO", "SI"),
    "QPPS-1005-AFI": ("DESARROLLO Y TRANSFORMACIÓN DE EQUIPO", "ACTUALIZACIÓN DE FORMATOS INTERNOS", "ESTE CÓDIGO SE UTILIZARÁ PARA REPORTAR LAS HORAS EFECTIVAS RELACIONADAS AL DISEÑO, ACTUALIZACIÓN Y/O REALIZACIÓN DE FORMATOS INTERNOS DEL ÁREA", "NO"),
    "QPPS-1006-DML": ("DISEÑO DE PRODUCTOS", "DISEÑO DE PROPUESTAS, ASESORÍA, REUNIONES COMERCIALES Y MATERIAL PARA LATAM", "ESTE CÓDIGO SE UTILIZARÁ PARA REPORTAR LAS HORAS EFECTIVAS RELACIONADAS AL DISEÑO Y/O REALIZACIÓN DE MATERIAL NUEVO PARA EMPRESAS LATAM", "SI"),
    "QPPS-1007-FE": ("DESARROLLO Y TRANSFORMACIÓN DE EQUIPO", "FORMACIÓN A EQUIPO PSICOSOCIAL", "ESTE CÓDIGO SE UTILIZARÁ PARA REPORTAR LAS HORAS EFECTIVAS RELACIONADAS A LOS ESPACIOS DE FORMACIÓN TÉCNICA", "NO"),
    "QPPS-1008-GA": ("DESARROLLO Y TRANSFORMACIÓN DE EQUIPO", "GESTIÓN ADMINISTRATIVA - ORDENES DE SERVICIO Y FACTURACIÓN", "ESTE CÓDIGO SE UTILIZARÁ PARA REPORTAR LAS HORAS EFECTIVAS DE LA GESTIÓN ADMINISTRATIVA", "NO"),
    "QPPS-1009-EJSMF": ("SERVICIO AL CLIENTE INTERNO", "ESTRATEGIA JUNTOS SOMOS MÁS FUERTES", "ESTE CÓDIGO SE UTILIZARÁ PARA REPORTAR LAS HORAS EFECTIVAS EN EL DESARROLLO DE MATERIAL PARA LA ESTRATEGIA", "SI"),
}

with tabs[0]:
    st.title("INDICADORES DE ÁREA")

    # Selección de fechas
    start_date = st.date_input("Fecha inicio", value=pd.to_datetime("2025-01-01"), key="area_start")
    end_date = st.date_input("Fecha fin", value=pd.to_datetime("2025-03-30"), key="area_end")

    # --- Gráfica FINAL: Comparación de Totales por Tipo ---
    st.subheader("Gestión del servicio")

    all_types = ['asignacion', 'programacion', 'ejecucion', 'soportes', 'facturacion']
    type_totals = {}

    for t in all_types:
        df_temp = get_api_data(start_date, end_date, t)
        col_to_sum = 'hours_quantity'
        total_val = df_temp[col_to_sum].sum()
        type_totals[t.capitalize()] = total_val

    df_type_totals = pd.DataFrame({
        'Tipo': list(type_totals.keys()),
        'Total': list(type_totals.values())
    })

    fig_final = px.bar(
        df_type_totals, x='Tipo', y='Total', text='Total',
        labels={'Tipo': 'Tipo', 'Total': 'Total'},
        title='Comparativa de Tipos en el Rango Seleccionado'
    )
    fig_final.update_traces(texttemplate='%{text}', textposition='outside')
    st.plotly_chart(fig_final, key="area_chart")  

    # ==========================
    # 🔹 Distribución Interna / Externa
    # ==========================
    st.subheader("Distribución de tareas internas/externas")

    df_asignacion = get_api_data(start_date, end_date, "asignacion")
    df_asignacion['internal'] = df_asignacion['order_name'].apply(lambda x: x.startswith('QPPS'))
    
    total_internal = df_asignacion[df_asignacion['internal']]['hours_quantity'].sum()
    total_external = df_asignacion[~df_asignacion['internal']]['hours_quantity'].sum()

    # Gráfico de pastel
    df_pie = pd.DataFrame({
        'Tipo': ['Internas (QPPS)', 'Externas'],
        'Total': [total_internal, total_external]
    })

    fig_pie = px.pie(
        df_pie, values='Total', names='Tipo', 
        title="Distribución de Asignaciones"
    )
    st.plotly_chart(fig_pie)

    # ==========================
    # 🔹 Tabla Consolidada de Códigos QPPS
    # ==========================
    st.subheader("Consolidado de Actividades Internas (QPPS)")

    df_qpps = df_asignacion[df_asignacion['order_name'].isin(QPPS_CODES.keys())]
    
    consolidated_data = []
    for _, row in df_qpps.iterrows():
        code = row['order_name']
        categoria, actividad, nota, facturacion = QPPS_CODES.get(code, ("", "", "", ""))
        consolidated_data.append({
            "CATEGORÍA": categoria,
            "NOMBRE ACTIVIDAD": actividad,
            "NOTA": nota,
            "CÓDIGO INTERNO": code,
            "FACTURACIÓN INTERNA": facturacion,
            "HORAS REPORTADAS": row['hours_quantity']
        })

    df_consolidado = pd.DataFrame(consolidated_data)

    # Mostrar tabla en Streamlit
    st.dataframe(df_consolidado)



with tabs[1]:
# Título de la página
    st.title("INDICADORES POR PSICÓLOGO")

    # Selección de fechas
    start_date = st.date_input("Fecha inicio", value=pd.to_datetime("2025-01-01"))
    end_date = st.date_input("Fecha fin", value=pd.to_datetime("2025-03-30"))

    # Selección del tipo
    selected_display = st.selectbox("Tipo", list(type_map.keys()), key="type_exe")
    selected_type = type_map[selected_display]
    # Cuando es facturación, se habilita la opción de visualizar por Monto o Horas
    if selected_type == "facturacion":
        metric_option = st.radio("Ver por:", options=["Horas", "Monto"])
        if metric_option == "Horas":
            metric_col = "hours_quantity"
            meta_value = 120
        else:
            metric_col = "amount"
            meta_value = 1000  # Meta arbitraria para monto
    else:
        metric_option = "Horas"  # Valor por defecto
        metric_col = "hours_quantity"
        meta_value = 120

    # Subtítulo dinámico
    st.subheader(f"Reporte de {selected_type} por Psicólogo")

    # Selección de agrupación para el eje X
    grouping_option = st.radio("Agrupar en eje X por:", options=["Mes", "Psicólogo"])

    # Obtener los datos "desde la API" (mock)
    df = get_api_data(start_date, end_date, selected_type)
    df['month'] = df['date'].dt.month.apply(lambda x: meses_es[x])

    # --- Gráfica 1: Total por Mes/Psicólogo con valores encima ---
    if grouping_option == "Mes":
        grouped = df.groupby(['month', 'executor'], as_index=False)[metric_col].sum()
        fig1 = px.bar(grouped, 
                    x='month', 
                    y=metric_col, 
                    color='executor', 
                    barmode='group',
                    text=metric_col,
                    labels={metric_col: "Total", "month": "Mes",  "executor": "Psicólogo"},
                    title=f"Total por Mes y Psicólogo ({metric_option if selected_type=='facturacion' else 'Horas'})")
        fig1.add_hline(y=meta_value, line_dash="dot", 
                        annotation_text=f"Meta {meta_value}", annotation_position="top right")
    else:
        grouped = df.groupby(['executor', 'month'], as_index=False)[metric_col].sum()
        fig1 = px.bar(grouped, 
                    x='executor', 
                    y=metric_col, 
                    color='month', 
                    barmode='group',
                    text=metric_col ,
                    labels={metric_col: "Total", "executor": "Psicólogo",  "month": "Mes"},
                    title=f"Total por Psicólogo y Mes ({metric_option if selected_type=='facturacion' else 'Horas'})")
        fig1.add_hline(y=meta_value, line_dash="dot", 
                        annotation_text=f"Meta {meta_value}", annotation_position="top right")
    
    fig1.update_traces(texttemplate='%{text}', textposition='outside')
    st.plotly_chart(fig1)

    # --- Gráfica 2: Porcentaje respecto a la meta ---
    grouped['percentage'] = grouped[metric_col] / meta_value * 100
    if grouping_option == "Mes":
        fig2 = px.bar(grouped, 
                    x='month', 
                    y='percentage', 
                    color='executor', 
                    barmode='group',
                    text='percentage',
                    labels={'percentage': 'Porcentaje (%)', "month": "Mes", "executor": "Psicólogo"},
                    title=f"Porcentaje respecto al 80% de la meta ({meta_value}) por Mes y Psicólogo")
        fig2.add_hline(y=80, line_dash="dot", 
                        annotation_text="Meta 80%", annotation_position="top right")
    else:
        fig2 = px.bar(grouped, 
                    x='executor', 
                    y='percentage', 
                    color='month', 
                    barmode='group',
                    text='percentage',
                    labels={'percentage': 'Porcentaje (%)', "executor": "Psicólogo", "month": "Mes"},
                    title=f"Porcentaje respecto a la meta ({meta_value}) por Psicólogo y Mes")
        fig2.add_hline(y=80, line_dash="dot", 
                        annotation_text="Meta 80%", annotation_position="top right")
    fig2.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
    st.plotly_chart(fig2)

    meta_data = [
        {'month': 'Ene', 'meta': 100},  # O "2025-01" si tu mes está en ese formato
        {'month': 'Feb', 'meta': 120},
        {'month': 'Mar', 'meta': 110},
    # Agrega más filas si tienes más meses
    ]
    meta_df = pd.DataFrame(meta_data)
    # 2. Unir (merge) las metas con el total real mes a mes
    # --- Gráfica 3: Total general mes a mes (sin discriminar por psicólogo y con línea de meta que varía mes a mes) ---
    total_mes = df.groupby('month', as_index=False)[metric_col].sum()
    merged = pd.merge(total_mes, meta_df, on='month', how='left')

    # --- Gráfica combinada ---
    # 1) Graficar la barra con px.bar
    fig4 = px.bar(
        total_mes,
        x='month',
        y=metric_col,
        labels={'month': 'Mes', metric_col: f"Total ({metric_option})"},
        title=f"Total ({metric_option}) vs Meta por Mes",
        text=metric_col
    )
    # 2) Añadir la traza tipo línea para la meta
    fig4.add_trace(
        go.Scatter(
            x=meta_df['month'],
            y=meta_df['meta'],
            mode='lines+markers',
            name='Meta'  # Nombre que saldrá en la leyenda
        )
    )

    st.plotly_chart(fig4)

    # resumen de horas
    # --- Gráfica FINAL: Comparación de Totales por Tipo (programación, ejecución, soportes y facturación) ---
    st.subheader("Gestión del servicio")

    # Definimos qué tipos vamos a graficar
    all_types = ['asignacion','programacion', 'ejecucion', 'soportes', 'facturacion']

    # Preparamos un diccionario para guardar las sumas de cada tipo
    type_totals = {}

    for t in all_types:
        # Para cada tipo, volvemos a pedir los datos según el rango seleccionado
        df_temp = get_api_data(start_date, end_date, t)
        
        col_to_sum = 'hours_quantity'
        
        total_val = df_temp[col_to_sum].sum()
        
        # Guardamos en el diccionario, para luego armar un DataFrame
        # Ponemos un nombre "amigable" con .capitalize() o tú lo cambias a tu gusto
        type_totals[t.capitalize()] = total_val

    # Convertimos el diccionario en DataFrame para graficar
    df_type_totals = pd.DataFrame({
        'Tipo': list(type_totals.keys()),
        'Total': list(type_totals.values())
    })

    # Graficamos con Plotly Express
    fig_final = px.bar(
        df_type_totals, 
        x='Tipo', 
        y='Total', 
        text='Total',
        labels={'Tipo': 'Tipo', 'Total': 'Total'},
        title='Comparativa de Tipos en el Rango Seleccionado'
    )
    fig_final.update_traces(texttemplate='%{text}', textposition='outside')
    st.plotly_chart(fig_final)  



# ---------------------------
# Pestaña [1]: POR EMPRESA
# ---------------------------
# ---------------------------
# Pestaña [1]: POR EMPRESA
# *** MODIFICADA ***
# ---------------------------
with tabs[2]:
    st.title("REPORTES POR EMPRESA")
    
    # 1) Fecha inicio/fin
    start_date_emp = st.date_input("Fecha inicio", key="start_emp", value=pd.to_datetime("2025-01-01"))
    end_date_emp = st.date_input("Fecha fin", key="end_emp", value=pd.to_datetime("2025-03-30"))
    
    # 2) Tipo (con opción de ver Horas / Monto si es facturación)
    selected_display_emp = st.selectbox("Tipo", list(type_map.keys()), key="type_emp")
    selected_type_emp = type_map[selected_display_emp]
    
    if selected_type_emp == "facturacion":
        metric_option_emp = st.radio("Ver por:", options=["Horas", "Monto"], key="radio_emp")
        if metric_option_emp == "Horas":
            metric_col_emp = "hours_quantity"
        else:
            metric_col_emp = "amount"
    else:
        metric_option_emp = "Horas"
        metric_col_emp = "hours_quantity"
    
    # 3) Seleccionar la empresa a consultar
    df_emp = get_api_data(start_date_emp, end_date_emp, selected_type_emp)
    company_options = df_emp['company'].unique()
    selected_company = st.selectbox("Empresa", company_options, key="company")
    
    st.subheader(f"Reporte de {selected_type_emp} para {selected_company}")
    
    # 4) Obtener los datos "desde la API" y filtrar solo la empresa

    df_emp = df_emp[df_emp['company'] == selected_company]
    
    # Nueva columna "month" para agrupar por mes si queremos
    df_emp['month'] = df['date'].dt.month.apply(lambda x: meses_es[x])

    
    # --- Gráfica 1: Totales por Mes (sin mostrar psicólogos) ---
    grouped_emp = df_emp.groupby('month', as_index=False)[metric_col_emp].sum()

    fig_emp_1 = px.bar(
        grouped_emp,
        x='month',
        y=metric_col_emp,
        labels={'month': 'Mes', metric_col_emp: f"Total ({metric_option_emp})"},
        title=f"Total ({metric_option_emp}) por Mes - {selected_company}"
    )

    st.plotly_chart(fig_emp_1)
    
    
    # --- Gráfica 3: Total general en el período seleccionado ---
    total_emp = df_emp[metric_col_emp].sum()  # Suma total en todo el período
    # Creamos un DataFrame con una fila para graficar de manera sencilla
    df_total_emp = pd.DataFrame({f"Total ({metric_option_emp})": [total_emp]}, index=[selected_company]).reset_index()
    df_total_emp.columns = ['Empresa', f"Total ({metric_option_emp})"]
    
    fig_emp_3 = px.bar(
        df_total_emp,
        x=f"Total ({metric_option_emp})",
        y='Empresa',
        orientation='h',
        title=f"Total {metric_option_emp} (Período seleccionado)"
    )
    st.plotly_chart(fig_emp_3)

    st.subheader("Distribución del progreso")

    # Definimos qué tipos vamos a graficar
    all_types = ['asignacion','programacion', 'ejecucion', 'soportes', 'facturacion']

    # Preparamos un diccionario para guardar las sumas de cada tipo
    type_totals = {}

    for t in all_types:
        # Para cada tipo, volvemos a pedir los datos según el rango seleccionado
        df_temp = get_api_data(start_date, end_date, t)

        # filter by company
        df_temp = df_temp[df_temp['company'] == selected_company]
        
        col_to_sum = 'hours_quantity'
        
        total_val = df_temp[col_to_sum].sum()
        
        # Guardamos en el diccionario, para luego armar un DataFrame
        # Ponemos un nombre "amigable" con .capitalize() o tú lo cambias a tu gusto
        type_totals[t.capitalize()] = total_val

    # Convertimos el diccionario en DataFrame para graficar
    df_type_totals = pd.DataFrame({
        'Tipo': list(type_totals.keys()),
        'Total': list(type_totals.values())
    })

    # Graficamos con Plotly Express
    fig_final = px.bar(
        df_type_totals, 
        x='Tipo', 
        y='Total', 
        text='Total',
        labels={'Tipo': 'Tipo', 'Total': 'Total'},
        title='Comparativa de Tipos en el Rango Seleccionado'
    )
    fig_final.update_traces(texttemplate='%{text}', textposition='outside')
    st.plotly_chart(fig_final)  

    # -----------------------------------------------------------------
    # NUEVO: Mostrar tabla con distribución de actividades si es 'ejecucion'
    # -----------------------------------------------------------------
    if selected_type_emp == "ejecucion":
        st.subheader("Distribución de Actividades")
        
        # Agrupa por la columna que guarda la actividad (usualmente 'execution_type')
        # y suma las horas correspondientes.
        activity_distribution = (
            df_emp.groupby('activity', dropna=False)['hours_quantity']
            .sum()
            .reset_index()
        )
        activity_distribution.columns = ["Tipo de Actividad", "Total de Horas"]

        st.write("Tabla de distribución de actividades para la empresa seleccionada:")
        st.dataframe(activity_distribution)


# --------------------------------
# Pestaña [2]: INDICADORES CLIENTE
# --------------------------------
with tabs[3]:
    st.title("INDICADORES POR CLIENTE")
    start_date_cli = st.date_input("Fecha inicio", key="start_cli", value=pd.to_datetime("2025-01-01"))
    end_date_cli = st.date_input("Fecha fin", key="end_cli", value=pd.to_datetime("2025-03-30"))
    
    selected_display_cli = st.selectbox("Tipo", list(type_map.keys()), key="type_cli")
    selected_type_cli = type_map[selected_display_cli]

    
    # Cuando es facturación, se habilita la opción de visualizar por Monto o Horas
    if selected_type_cli == "facturacion":
        metric_option_cli = st.radio("Ver por:", options=["Horas", "Monto"], key="radio_cli")
        if metric_option_cli == "Horas":
            metric_col_cli = "hours_quantity"
        else:
            metric_col_cli = "amount"
    else:
        metric_option_cli = "Horas"
        metric_col_cli = "hours_quantity"

    st.subheader(f"Reporte de {selected_type_cli} por Cliente")
    grouping_option_cli = st.radio("Agrupar en eje X por:", options=["Mes", "Cliente/Tipo"], key="group_cli")
    
    df_cli = get_api_data(start_date_cli, end_date_cli, selected_type_cli)
    # Nueva columna: si client_type es "arl", se usa el valor de client; si no, se usa client_type.
    df_cli['group_client'] = df_cli.apply(lambda row: row['client'] if row['client_type'] == 'arl' else row['client_type'], axis=1)
    # df_cli['month'] = df_cli['date'].dt.to_period('M').astype(str)

    df_cli['month'] = df['date'].dt.month.apply(lambda x: meses_es[x])

    
    # --- Gráfica 1 ---
    if grouping_option_cli == "Mes":
        grouped_cli = df_cli.groupby(['month', 'group_client'], as_index=False)[metric_col_cli].sum()
        fig1_cli = px.bar(grouped_cli,
                          x='month',
                          y=metric_col_cli,
                          color='group_client',
                          barmode='group',
                          labels={metric_col_cli: f"Total ({metric_option_cli})", 'month': 'Mes', 'group_client': 'Cliente'},
                          title=f"{metric_option_cli} Totales por Mes y Cliente/Tipo")
    else:
        grouped_cli = df_cli.groupby(['group_client', 'month'], as_index=False)[metric_col_cli].sum()
        fig1_cli = px.bar(grouped_cli,
                          x='group_client',
                          y=metric_col_cli,
                          color='month',
                          barmode='group',
                          labels={metric_col_cli: f"Total ({metric_option_cli})", 'group_client': 'Cliente', 'month': 'Mes'},
                          title=f"{metric_option_cli} Totales por Cliente/Tipo y Mes")
    st.plotly_chart(fig1_cli)
    

    # --- Gráfica 3: Total general ---
    total_cli = df_cli.groupby('group_client', as_index=False)[metric_col_cli].sum()
    fig3_cli = px.bar(total_cli,
                      x=metric_col_cli,
                      y='group_client',
                      orientation='h',
                      labels={metric_col_cli: f"Total ({metric_option_cli})", 'group_client': 'Cliente/Tipo'},
                      title=f"Total {metric_option_cli} por Cliente/Tipo")
    st.plotly_chart(fig3_cli)

        # --- GRÁFICA EXTRA: COMPARACIÓN POR CLIENTE DE 4 TIPOS (PROGRAMACIÓN, EJECUCIÓN, SOPORTES, FACTURACIÓN) ---
    st.subheader("Comparación de Totales (Programación, Ejecución, Soportes, Facturación) por Cliente")

    # 1) Definimos la lista de tipos a comparar
    tipos = ['asignacion','programacion', 'ejecucion', 'soportes', 'facturacion']

    # 2) Creamos una lista para ir acumulando los DF individuales
    dfs_list = []

    for t in tipos:
        # Llamamos a la API para cada tipo, usando el mismo rango de fechas
        df_temp = get_api_data(start_date_cli, end_date_cli, t).copy()
        
        # Aplicamos la misma lógica de 'group_client'
        df_temp['group_client'] = df_temp.apply(
            lambda row: row['client'] if row['client_type'] == 'arl' else row['client_type'], 
            axis=1
        )
        
        # Decidimos qué columna sumar
        # - Si es facturación, usamos lo que haya seleccionado el usuario (Horas o Monto)
        # - Para los demás (programación, ejecución, soportes), usamos hours_quantity
        if t == 'facturacion':
            col_to_sum = metric_col_cli  # hours_quantity o amount, según radio del usuario
        else:
            col_to_sum = 'hours_quantity'
        
        # Agrupamos por cliente y sumamos la columna correspondiente
        grouped_t = df_temp.groupby('group_client', as_index=False)[col_to_sum].sum()
        
        # Renombramos la columna a un nombre genérico (p.ej. 'value') para unificar
        grouped_t.rename(columns={col_to_sum: 'value'}, inplace=True)
        
        # Añadimos una columna 'tipo' para identificar de cuál de los 4 tipos proviene
        grouped_t['tipo'] = t.capitalize()  # O usa t en español si prefieres
        
        # Acumulamos este DF en la lista
        dfs_list.append(grouped_t)

    # 3) Concatenamos todos los DF en uno solo
    df_all_types = pd.concat(dfs_list, ignore_index=True)  
    # => Columnas finales: [group_client, value, tipo]

    # 4) Graficamos: barra agrupada (cada cliente tiene 4 barras)
    fig_cli_compare = px.bar(
        df_all_types,
        x='group_client',
        y='value',
        color='tipo',
        barmode='group',
        labels={
            'group_client': 'Cliente/Tipo', 
            'value': 'Total (Horas/Monto)', 
            'tipo': 'Tipo'
        },
        title='Comparación por Cliente: Programación, Ejecución, Soportes, Facturación'
    )
    st.plotly_chart(fig_cli_compare)



