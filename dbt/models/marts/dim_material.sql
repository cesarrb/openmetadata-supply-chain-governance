select
    mp.material_id || '|' || mp.plant_id as material_plant_key,
    m.material_id,
    mp.plant_id,
    m.material_description,
    m.material_type,
    m.material_group,
    m.base_uom,
    mp.mrp_controller,
    mp.planned_lead_time_days,
    mp.safety_stock_qty,
    mp.standard_price_eur,
    m.is_active
from {{ ref('stg_material') }} m
join {{ ref('stg_material_plant') }} mp on mp.material_id = m.material_id
