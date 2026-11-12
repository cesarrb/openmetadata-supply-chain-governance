select
    matnr   as material_id,
    werks   as plant_id,
    dispo   as mrp_controller,
    plifz   as planned_lead_time_days,
    eisbe   as safety_stock_qty,
    stprs   as standard_price_eur
from {{ source('sap_erp', 'marc') }}
