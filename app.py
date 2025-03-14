import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import ssl
import xmlrpc.client
import pandas as pd

ODOO_URL = 'https://quiron.centralus.cloudapp.azure.com/'  # o 'http://localhost:8069'
ODOO_DB = 'quiron_odoo'
ODOO_USERNAME = 'admin'
ODOO_PASSWORD = 'admin'

# Desactivamos la verificación SSL sólo si es necesario
ssl_context = ssl._create_unverified_context()

def get_odoo_connection():
    """
    Devuelve (common, uid, models) para interactuar con Odoo vía XML-RPC.
    """
    common = xmlrpc.client.ServerProxy(
        f'{ODOO_URL}xmlrpc/2/common',
        context=ssl_context
    )
    uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(
        f'{ODOO_URL}xmlrpc/2/object',
        context=ssl_context
    )
    return common, uid, models

def get_api_data_odoo(start_date, end_date, selected_type):
    """
    Retorna un DataFrame con las columnas:
    ['date', 'order_name', 'execution_type', 'executor', 'hours_quantity',
     'observation', 'company', 'client', 'client_type', 'type', 'amount']
    filtrado por la fecha y el 'selected_type'.
    
    :param start_date: datetime.date o string 'YYYY-MM-DD' inicio
    :param end_date: datetime.date o string 'YYYY-MM-DD' fin
    :param selected_type: str en ['programacion', 'ejecucion', 'soportes', 'facturacion']
    :return: pd.DataFrame
    """
    # Conexión a Odoo
    common, uid, models = get_odoo_connection()

    # Mapeo: el "selected_type" de la app vs. el modelo Odoo y campo de fecha
    # -----------------------------------------------------------------------
    #  programacion -> so.programming (filtrar por activity_date)
    #  ejecucion    -> so.register    (filtrar por execution_date)
    #  soportes     -> so.execution   (filtrar por execution_date)
    #  facturacion  -> so.billing     (filtrar por billing_date)
    #
    # hours_quantity -> 
    #   * programacion: hours_quantity
    #   * ejecucion   : hours_quantity
    #   * soportes    : hours_quantity
    #   * facturacion : quantity (renombrar a hours_quantity = quantity)
    #
    # amount ->
    #   * facturacion: total
    #   * si no es facturación: 0
    #
    # date ->
    #   * programacion: activity_date
    #   * ejecucion   : execution_date (Date)
    #   * soportes    : execution_date (Datetime)
    #   * facturacion : billing_date
    #

    if selected_type == "programacion":
        odoo_model = "so.programming"
        date_field = "activity_date"
        hours_field = "hours_quantity"  # float
        amount_field = None
    elif selected_type == "ejecucion":
        odoo_model = "so.register"
        date_field = "execution_date"
        hours_field = "hours_quantity"
        amount_field = None
    elif selected_type == "soportes":
        odoo_model = "so.execution"
        date_field = "execution_date"
        hours_field = "hours_quantity"
        amount_field = None
    elif selected_type == "facturacion":
        odoo_model = "so.billing"
        date_field = "billing_date"
        hours_field = "quantity"
        amount_field = "total"
    else:
        # Caso de seguridad; si llega un tipo desconocido, retornar DF vacío
        return pd.DataFrame(columns=[
            "date", "order_name", "execution_type", "executor", "hours_quantity",
            "observation", "company", "client", "client_type", "type", "amount"
        ])

    # Dominio (filtro) para las fechas
    # date_field >= start_date and date_field <= end_date
    domain = [
        (date_field, '>=', str(start_date)),
        (date_field, '<=', str(end_date)),
    ]

    # Campos que queremos leer directamente en la "search_read"
    # - order_id.* se requiere si Odoo lo soporta en la misma lectura.
    fields_to_read = [
        'id',
        date_field,
        # Para order_id, si Odoo 14+ normalmente no hace la lectura anidada a order_id.xxx
        # pero ponemos 'order_id' para obtener (id, name). 
        'order_id',
        # En cada modelo existen varios, por ejemplo en "so.execution" hay "execution_type", etc.
        # Ponemos todos para luego mapearlos manualmente:
        'execution_type',      # en so.execution o so.register
        'hours_quantity',      # en so.execution, so.register, so.programming
        'quantity',            # en so.billing
        'total',               # en so.billing
        'concept',             # en so.programming
        'status',              # en so.programming
        'observation',         # en so.execution, so.register
    ]
    # No olvides que si Odoo no encuentra esos campos, podría dar error.  
    # Puedes modularizar según el modelo. Este es un ejemplo genérico.

    # Realizamos el search_read
    records = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        odoo_model, 'search_read',
        [domain],  # búsqueda con el dominio
        {'fields': fields_to_read, 'limit': 10000}  # ejemplo: limit grande
    )

    # Ahora, por cada registro, consultamos su "mrp.production" (order_id) 
    # para obtener company_executed, client, client_type y nombre de la orden.
    # -------------------------------------------------------------------------
    #   order_id => (id, "Nombre de la orden"?)
    #   Pero necesitamos fields: ['name', 'order_number', 'client', 'client_type', 'company_executed']
    #
    # Sugerencia: si son muchos registros, conviene obtener primero todos los 'order_id' únicos,
    # hacerles read_batch en mrp.production, y luego mapear. Abajo se muestra la forma simple (uno a uno).

    # 1) recolectar IDs de order_id
    order_ids = [rec['order_id'][0] for rec in records if rec.get('order_id')]
    order_ids_unicos = list(set(order_ids))

    # 2) leer en bloque la mrp.production
    order_fields = ['name', 'order_number', 'client_type', 'client', 'company_executed']
    orders_data = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        'mrp.production', 'search_read',
        [[('id', 'in', order_ids_unicos)]],
        {'fields': order_fields, 'limit': len(order_ids_unicos)}
    )
    # Creamos un dict {order_id: {...campos...}}
    orders_dict = {od['id']: od for od in orders_data}

    # Construimos la lista final unificada:
    result_list = []

    for r in records:
        # Dependiendo del modelo, 'date' vendrá del campo "date_field"
        record_date = r.get(date_field)

        # Horas
        if hours_field:
            hrs = r.get(hours_field, 0.0)
        else:
            hrs = 0.0

        # Monto (solo si facturación)
        if amount_field:
            amt = r.get(amount_field, 0.0)
        else:
            amt = 0.0

        # execution_type => en so.execution / so.register
        # en so.programming => no existe un "execution_type" como tal, 
        #   podrías mapear "concept" o "status". 
        #   Si te interesa un campo textual, ajústalo aquí.
        exec_type = r.get('execution_type', '')
        if selected_type == 'programacion':
            # Podríamos usar concept o status
            exec_type = r.get('concept', '')

        # observation => so.register, so.execution lo tienen.
        # en programacion no lo hay, podríamos poner `status` como "observación" 
        obs = r.get('observation', '')
        if selected_type == 'programacion':
            obs = r.get('status', '')

        # Leemos la order_id para extraer: name, client_type, client, company_executed
        order_info = {}
        if r.get('order_id'):
            oid = r['order_id'][0]
            order_info = orders_dict.get(oid, {})

        # order_name => preferimos 'order_number' si existe, sino 'name'
        order_name = order_info.get('order_number') or order_info.get('name', '')

        # client_type => 'arl', 'delima', 'directo', etc.
        ctype = order_info.get('client_type', '')

        # client => Many2one
        # Esto si te devuelve (id, name) en Odoo 14+ o si no, tendrás que hacer otra lectura
        # Suponiendo que se guardó en la DB como (id)...
        client_id = order_info.get('client', False)
        client_name = ''
        if isinstance(client_id, list) and len(client_id) == 2:
            client_name = client_id[1]
        # company => en la orden es "company_executed"
        comp_id = order_info.get('company_executed', False)
        company_name = ''
        if isinstance(comp_id, list) and len(comp_id) == 2:
            company_name = comp_id[1]

        # executor => no lo tenemos en "so.common". Ajusta si existe un campo 'responsible_id' 
        # o algo similar. En este ejemplo lo dejamos vacío:
        executor_name = ''

        result_list.append({
            "date": record_date or "",  
            "order_name": order_name,
            "execution_type": exec_type,
            "executor": executor_name, 
            "hours_quantity": hrs,
            "observation": obs,
            "company": company_name,
            "client": client_name,
            "client_type": ctype,
            "type": selected_type,
            "amount": amt
        })

    # Convertimos a DataFrame
    df = pd.DataFrame(result_list, columns=[
        "date", "order_name", "execution_type", "executor", "hours_quantity",
        "observation", "company", "client", "client_type", "type", "amount"
    ])

    # Opcional: convertir la columna "date" a datetime (si Odoo la retorna como string)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')

    return df


def get_api_data(start_date, end_date, selected_type):
    # Datos de ejemplo "hardcodeados" para simular la respuesta de la API
    # Número de muestras
    num_samples = 100

    # Generar fechas entre el 1 de enero de 2025 y el 31 de marzo de 2025
    dates = pd.date_range(start="2025-01-01", end="2025-03-31", freq='D')
    sample_dates = np.random.choice(dates, size=num_samples)

    # Crear la data de muestra
    df = pd.DataFrame({
        "date": sample_dates,
        "order_name": [f"order_{i+1}" for i in range(num_samples)],
        "execution_type": np.random.choice(["Tipo A", "Tipo B"], size=num_samples),
        "executor": np.random.choice(["Psicologo 1", "Psicologo 2", "Psicologo 3"], size=num_samples),
        "hours_quantity": np.random.randint(1, 10, size=num_samples),
        "observation": np.random.choice(["Observacion 1", "Observacion 2", "Observacion 3"], size=num_samples),
        "company": np.random.choice(["EmpresaA", "EmpresaB", "EmpresaC"], size=num_samples),
        "client": np.random.choice(["Cliente1", "Cliente2", "Cliente3"], size=num_samples),
        "client_type": np.random.choice(["ARL", "DIRECTO", "DELIMA"], size=num_samples),
        "type": np.random.choice(["ejecucion", "programacion", "soportes", "facturacion"], size=num_samples),
        "amount": np.random.randint(3000, 2000000)
    })

    # Convertir a datetime
    df['date'] = pd.to_datetime(df['date'])

    # --- Modificación solicitada ---
    # Si el client_type es ARL, asigna a 'client' un valor aleatorio de [SURA, COLMENA, BOLIVAR]
    mask_arl = (df['client_type'] == 'ARL')
    df.loc[mask_arl, 'client'] = np.random.choice(["SURA", "COLMENA", "BOLIVAR"], size=mask_arl.sum())

    # Filtrar los datos según el rango de fechas y el tipo seleccionado
    df = df[(df['date'] >= pd.to_datetime(start_date)) & (df['date'] <= pd.to_datetime(end_date))]
    df = df[df['type'] == selected_type]
    return df


tabs = st.tabs(["Indicadores por Psicólogo", "Indicadores por Empresa", "Indicadores por Cliente"])


with tabs[0]:
# Título de la página
    st.title("INDICADORES POR PSICÓLOGO")

    # Selección de fechas
    start_date = st.date_input("Fecha inicio", value=pd.to_datetime("2025-01-01"))
    end_date = st.date_input("Fecha fin", value=pd.to_datetime("2025-03-30"))

    # Selección del tipo
    type_options = ['ejecucion', 'programacion', 'soportes', 'facturacion']
    selected_type = st.selectbox("Tipo", type_options)

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
    st.subheader(f"Reporte de {selected_type}")

    # Selección de agrupación para el eje X
    grouping_option = st.radio("Agrupar en eje X por:", options=["Mes", "Psicólogo"])

    # Obtener los datos "desde la API" (mock)
    df = get_api_data(start_date, end_date, selected_type)
    df['month'] = df['date'].dt.to_period('M').astype(str)

    # --- Gráfica 1: Total por Mes/Psicólogo con valores encima ---
    if grouping_option == "Mes":
        grouped = df.groupby(['month', 'executor'], as_index=False)[metric_col].sum()
        fig1 = px.bar(grouped, 
                    x='month', 
                    y=metric_col, 
                    color='executor', 
                    barmode='group',
                    text=metric_col,
                    labels={metric_col: "Total", "month": "Mes"},
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
                    text=metric_col,
                    labels={metric_col: "Total", "executor": "Psicólogo"},
                    title=f"Total por Psicólogo y Mes ({metric_option if selected_type=='facturacion' else 'Horas'})")
        fig1.add_hline(y=meta_value, line_dash="dot", 
                        annotation_text=f"Meta {meta_value}", annotation_position="top right")
    fig1.update_traces(texttemplate='%{text}')
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
                    labels={'percentage': 'Porcentaje (%)', "month": "Mes"},
                    title=f"Porcentaje respecto a la meta ({meta_value}) por Mes y Psicólogo")
        fig2.add_hline(y=100, line_dash="dot", 
                        annotation_text="Meta 100%", annotation_position="top right")
    else:
        fig2 = px.bar(grouped, 
                    x='executor', 
                    y='percentage', 
                    color='month', 
                    barmode='group',
                    text='percentage',
                    labels={'percentage': 'Porcentaje (%)', "executor": "Psicólogo"},
                    title=f"Porcentaje respecto a la meta ({meta_value}) por Psicólogo y Mes")
        fig2.add_hline(y=100, line_dash="dot", 
                        annotation_text="Meta 100%", annotation_position="top right")
    fig2.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
    st.plotly_chart(fig2)

    # --- Gráfica 3: Total general por Psicólogo ---
    total_general = df.groupby('executor', as_index=False)[metric_col].sum()
    fig3 = px.bar(total_general, 
                x=metric_col, 
                y='executor', 
                orientation='h',
                text=metric_col,
                labels={metric_col: "Total", "executor": "Psicólogo"},
                title=f"Total General por Psicólogo ({metric_option if selected_type=='facturacion' else 'Horas'})")
    fig3.update_traces(texttemplate='%{text}', textposition='outside')
    st.plotly_chart(fig3)   


    # --- Gráfica 3: Total general mes a mes (sin discriminar por psicólogo y con línea de meta que varía mes a mes) ---
    total_mes = df.groupby('month', as_index=False)[metric_col].sum()
    fig4 = px.bar(total_mes,
                x='month',
                y=metric_col,
                labels={'month': 'Mes', metric_col: f"Total ({metric_option})"},
                title=f"Total ({metric_option}) por Mes")
    fig4.add_hline(
        y=meta_value,
        line_dash="dot",
        annotation_text=f"Meta {meta_value}",
        annotation_position="top right"
    )
    st.plotly_chart(fig4)


# ---------------------------
# Pestaña [1]: POR EMPRESA
# ---------------------------
# ---------------------------
# Pestaña [1]: POR EMPRESA
# *** MODIFICADA ***
# ---------------------------
with tabs[1]:
    st.title("REPORTES POR EMPRESA")
    
    # 1) Fecha inicio/fin
    start_date_emp = st.date_input("Fecha inicio", key="start_emp", value=pd.to_datetime("2025-01-01"))
    end_date_emp = st.date_input("Fecha fin", key="end_emp", value=pd.to_datetime("2025-03-30"))
    
    # 2) Tipo (con opción de ver Horas / Monto si es facturación)
    type_options_emp = ['ejecucion', 'programacion', 'soportes', 'facturacion']
    selected_type_emp = st.selectbox("Tipo", type_options_emp, key="type_emp")
    
    if selected_type_emp == "facturacion":
        metric_option_emp = st.radio("Ver por:", options=["Horas", "Monto"], key="radio_emp")
        if metric_option_emp == "Horas":
            metric_col_emp = "hours_quantity"
            meta_value_emp = 120
        else:
            metric_col_emp = "amount"
            meta_value_emp = 1000
    else:
        metric_option_emp = "Horas"
        metric_col_emp = "hours_quantity"
        meta_value_emp = 120
    
    # 3) Seleccionar la empresa a consultar
    company_options = ["EmpresaA", "EmpresaB", "EmpresaC"]
    selected_company = st.selectbox("Empresa", company_options, key="company")
    
    st.subheader(f"Reporte de {selected_type_emp} para {selected_company}")
    
    # 4) Obtener los datos "desde la API" y filtrar solo la empresa
    df_emp = get_api_data(start_date_emp, end_date_emp, selected_type_emp)
    df_emp = df_emp[df_emp['company'] == selected_company]
    
    # Nueva columna "month" para agrupar por mes si queremos
    df_emp['month'] = df_emp['date'].dt.to_period('M').astype(str)
    
    # --- Gráfica 1: Totales por Mes (sin mostrar psicólogos) ---
    grouped_emp = df_emp.groupby('month', as_index=False)[metric_col_emp].sum()

    fig_emp_1 = px.bar(
        grouped_emp,
        x='month',
        y=metric_col_emp,
        labels={'month': 'Mes', metric_col_emp: f"Total ({metric_option_emp})"},
        title=f"Total ({metric_option_emp}) por Mes - {selected_company}"
    )
    fig_emp_1.add_hline(
        y=meta_value_emp, 
        line_dash="dot", 
        annotation_text=f"Meta {meta_value_emp}", 
        annotation_position="top right"
    )
    st.plotly_chart(fig_emp_1)
    
    # --- Gráfica 2: Porcentaje respecto a la meta (por Mes) ---
    grouped_emp['percentage'] = grouped_emp[metric_col_emp] / meta_value_emp * 100
    
    fig_emp_2 = px.bar(
        grouped_emp,
        x='month',
        y='percentage',
        labels={'month': 'Mes', 'percentage': 'Porcentaje respecto a meta (%)'},
        title=f"Porcentaje de Meta por Mes - {selected_company}"
    )
    fig_emp_2.add_hline(
        y=100,
        line_dash="dot",
        annotation_text="Meta 100%",
        annotation_position="top right"
    )
    st.plotly_chart(fig_emp_2)
    
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
# --------------------------------
# Pestaña [2]: INDICADORES CLIENTE
# --------------------------------
with tabs[2]:
    st.title("INDICADORES POR CLIENTE")
    start_date_cli = st.date_input("Fecha inicio", key="start_cli", value=pd.to_datetime("2025-01-01"))
    end_date_cli = st.date_input("Fecha fin", key="end_cli", value=pd.to_datetime("2025-03-30"))
    
    type_options_cli = ['ejecucion', 'programacion', 'soportes', 'facturacion']
    selected_type_cli = st.selectbox("Tipo", type_options_cli, key="type_cli")
    
    # Cuando es facturación, se habilita la opción de visualizar por Monto o Horas
    if selected_type_cli == "facturacion":
        metric_option_cli = st.radio("Ver por:", options=["Horas", "Monto"], key="radio_cli")
        if metric_option_cli == "Horas":
            metric_col_cli = "hours_quantity"
            meta_value_cli = 120
        else:
            metric_col_cli = "amount"
            meta_value_cli = 1000
    else:
        metric_option_cli = "Horas"
        metric_col_cli = "hours_quantity"
        meta_value_cli = 120

    st.subheader(f"Reporte de {selected_type_cli} por Cliente")
    grouping_option_cli = st.radio("Agrupar en eje X por:", options=["Mes", "Cliente/Tipo"], key="group_cli")
    
    df_cli = get_api_data(start_date_cli, end_date_cli, selected_type_cli)
    # Nueva columna: si client_type es "ARL", se usa el valor de client; si no, se usa client_type.
    df_cli['group_client'] = df_cli.apply(lambda row: row['client'] if row['client_type'] == 'ARL' else row['client_type'], axis=1)
    df_cli['month'] = df_cli['date'].dt.to_period('M').astype(str)
    
    # --- Gráfica 1 ---
    if grouping_option_cli == "Mes":
        grouped_cli = df_cli.groupby(['month', 'group_client'], as_index=False)[metric_col_cli].sum()
        fig1_cli = px.bar(grouped_cli,
                          x='month',
                          y=metric_col_cli,
                          color='group_client',
                          barmode='group',
                          labels={metric_col_cli: f"Total ({metric_option_cli})", 'month': 'Mes'},
                          title=f"{metric_option_cli} Totales por Mes y Cliente/Tipo")
        fig1_cli.add_hline(y=meta_value_cli, line_dash="dot", 
                           annotation_text=f"Meta {meta_value_cli}", annotation_position="top right")
    else:
        grouped_cli = df_cli.groupby(['group_client', 'month'], as_index=False)[metric_col_cli].sum()
        fig1_cli = px.bar(grouped_cli,
                          x='group_client',
                          y=metric_col_cli,
                          color='month',
                          barmode='group',
                          labels={metric_col_cli: f"Total ({metric_option_cli})", 'group_client': 'Cliente/Tipo'},
                          title=f"{metric_option_cli} Totales por Cliente/Tipo y Mes")
        fig1_cli.add_hline(y=meta_value_cli, line_dash="dot", 
                           annotation_text=f"Meta {meta_value_cli}", annotation_position="top right")
    st.plotly_chart(fig1_cli)
    
    # --- Gráfica 2: Porcentaje respecto a la meta ---
    grouped_cli['percentage'] = grouped_cli[metric_col_cli] / meta_value_cli * 100
    if grouping_option_cli == "Mes":
        fig2_cli = px.bar(grouped_cli,
                          x='month',
                          y='percentage',
                          color='group_client',
                          barmode='group',
                          labels={'percentage': 'Porcentaje respecto a meta (%)', 'month': 'Mes'},
                          title="Porcentaje de Meta por Mes y Cliente/Tipo")
        fig2_cli.add_hline(y=100, line_dash="dot", 
                           annotation_text="Meta 100%", annotation_position="top right")
    else:
        fig2_cli = px.bar(grouped_cli,
                          x='group_client',
                          y='percentage',
                          color='month',
                          barmode='group',
                          labels={'percentage': 'Porcentaje respecto a meta (%)', 'group_client': 'Cliente/Tipo'},
                          title="Porcentaje de Meta por Cliente/Tipo y Mes")
        fig2_cli.add_hline(y=100, line_dash="dot", 
                           annotation_text="Meta 100%", annotation_position="top right")
    st.plotly_chart(fig2_cli)
    
    # --- Gráfica 3: Total general ---
    total_cli = df_cli.groupby('group_client', as_index=False)[metric_col_cli].sum()
    fig3_cli = px.bar(total_cli,
                      x=metric_col_cli,
                      y='group_client',
                      orientation='h',
                      labels={metric_col_cli: f"Total ({metric_option_cli})", 'group_client': 'Cliente/Tipo'},
                      title=f"Total {metric_option_cli} por Cliente/Tipo")
    st.plotly_chart(fig3_cli)


# Botón de imprimir usando HTML y JavaScript (para todas las pestañas)
st.markdown("""
    <style>
    .print-button {
        background-color: #4CAF50;
        color: white;
        padding: 8px 16px;
        border: none;
        cursor: pointer;
        font-size: 16px;
    }
    </style>
    <button class="print-button" onclick="window.print()">Imprimir</button>
    """, unsafe_allow_html=True)

