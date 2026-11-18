-- Singular test: if (almost) every material-month shows 100 % forecast accuracy, the formula is
-- broken (e.g. integer division), not the forecast. Real accuracy at this grain is far below 95 %.
select avg(forecast_accuracy) as avg_accuracy
from {{ ref('fct_plan_vs_actual') }}
having avg(forecast_accuracy) > 0.95
