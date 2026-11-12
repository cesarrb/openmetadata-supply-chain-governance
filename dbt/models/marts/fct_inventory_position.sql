-- Inventory position per material/plant with value, safety-stock coverage and
-- Days of Inventory (DOI) based on the average daily demand of the last 90 days.
with stock as (
    select material_id, plant_id, sum(unrestricted_stock_qty) as stock_qty
    from {{ ref('stg_stock') }}
    group by 1, 2
),
demand as (
    select material_id, plant_id, sum(ordered_qty) / 90.0 as avg_daily_demand
    from {{ ref('stg_sales_order_line') }}
    where order_date > (select max(order_date) from {{ ref('stg_sales_order_line') }}) - 90
    group by 1, 2
)
select
    m.material_plant_key,
    m.material_id,
    m.plant_id,
    m.material_group,
    s.stock_qty,
    s.stock_qty * m.standard_price_eur                    as stock_value_eur,
    m.safety_stock_qty,
    (s.stock_qty < m.safety_stock_qty)                    as below_safety_stock,
    d.avg_daily_demand,
    case when coalesce(d.avg_daily_demand, 0) = 0 then null
         else round(s.stock_qty / d.avg_daily_demand, 1) end as days_of_inventory
from {{ ref('dim_material') }} m
join stock s using (material_id, plant_id)
left join demand d using (material_id, plant_id)
