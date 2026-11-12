-- Plan vs Actual: monthly consensus demand plan against actual order intake,
-- per material and plant. Forecast accuracy = 1 - |actual - plan| / actual.
with actual as (
    select material_id, plant_id,
           date_trunc('month', order_date)::date as plan_month,
           sum(ordered_qty) as actual_qty
    from {{ ref('stg_sales_order_line') }}
    where order_type = 'OR'
    group by 1, 2, 3
)
select
    p.material_id,
    p.plant_id,
    p.plan_month,
    p.plan_version,
    p.planned_qty,
    coalesce(a.actual_qty, 0)                           as actual_qty,
    coalesce(a.actual_qty, 0) - p.planned_qty           as variance_qty,
    case when coalesce(a.actual_qty, 0) = 0 then null
         else greatest(0, 1 - abs(a.actual_qty - p.planned_qty) / a.actual_qty)
    end::double precision                               as forecast_accuracy
from {{ ref('stg_demand_plan') }} p
left join actual a using (material_id, plant_id, plan_month)
