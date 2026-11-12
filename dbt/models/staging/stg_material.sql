select
    matnr       as material_id,
    maktx       as material_description,
    mtart       as material_type,
    matkl       as material_group,
    meins       as base_uom,
    brgew       as gross_weight_kg,
    is_active
from {{ source('sap_erp', 'mara') }}
