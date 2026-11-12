select
    h.vbeln      as delivery_id,
    i.posnr      as delivery_item,
    i.vgbel      as sales_order_id,
    i.vgpos      as sales_order_item,
    h.werks      as plant_id,
    i.matnr      as material_id,
    i.lfimg      as delivered_qty,
    h.wadat_ist  as actual_goods_issue_date
from {{ source('sap_erp', 'likp') }} h
join {{ source('sap_erp', 'lips') }} i on i.vbeln = h.vbeln
