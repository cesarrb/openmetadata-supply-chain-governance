select
    matnr        as material_id,
    werks        as plant_id,
    plan_month,
    planned_qty,
    plan_version
from {{ source('sap_erp', 'demand_plan') }}
