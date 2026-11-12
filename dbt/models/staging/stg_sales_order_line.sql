select
    h.vbeln  as sales_order_id,
    i.posnr  as sales_order_item,
    h.kunnr  as customer_id,
    h.erdat  as order_date,
    h.vdatu  as requested_delivery_date,
    h.auart  as order_type,
    i.matnr  as material_id,
    i.werks  as plant_id,
    i.kwmeng as ordered_qty,
    i.netpr  as net_price
from {{ source('sap_erp', 'vbak') }} h
join {{ source('sap_erp', 'vbap') }} i on i.vbeln = h.vbeln
