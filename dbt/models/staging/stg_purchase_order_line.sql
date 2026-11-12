select
    h.ebeln          as purchase_order_id,
    i.ebelp          as purchase_order_item,
    h.lifnr          as vendor_id,
    h.bedat          as order_date,
    h.bsart          as order_type,
    h.waers          as currency,
    i.matnr          as material_id,
    i.werks          as plant_id,
    i.menge          as ordered_qty,
    i.netpr          as net_price,
    i.menge * i.netpr as order_value,
    i.eindt          as agreed_delivery_date
from {{ source('sap_erp', 'ekko') }} h
join {{ source('sap_erp', 'ekpo') }} i on i.ebeln = h.ebeln
