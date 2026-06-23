// Pure incrementality → money math. Turns the cumulative causal effect (total
// incremental metric units over the post-period) plus user-supplied unit economics
// into iROAS, cost-per-incremental, net profit and ROI — with a range carried
// through from the effect's confidence interval.

export interface RoiInputs {
  spend: number          // total campaign spend over the post-period
  valuePerUnit: number   // revenue per incremental metric unit (1 if the metric is already revenue)
  marginPct: number      // gross margin %, to convert incremental revenue to profit
}

export interface RoiOutput {
  units: number; unitsLow: number; unitsHigh: number
  revenue: number
  profit: number
  iroas: number; iroasLow: number; iroasHigh: number
  costPerUnit: number
  netProfit: number; netLow: number; netHigh: number
  roiPct: number
}

const safeDiv = (a: number, b: number) => (Math.abs(b) > 1e-9 ? a / b : NaN)

export function computeRoi(
  cumFinal: number, cumLow: number, cumHigh: number, inp: RoiInputs,
): RoiOutput {
  const m = inp.marginPct / 100
  const rev = (u: number) => u * inp.valuePerUnit
  const profit = (u: number) => rev(u) * m
  const net = (u: number) => profit(u) - inp.spend
  return {
    units: cumFinal, unitsLow: cumLow, unitsHigh: cumHigh,
    revenue: rev(cumFinal),
    profit: profit(cumFinal),
    iroas: safeDiv(rev(cumFinal), inp.spend),
    iroasLow: safeDiv(rev(cumLow), inp.spend),
    iroasHigh: safeDiv(rev(cumHigh), inp.spend),
    costPerUnit: safeDiv(inp.spend, cumFinal),
    netProfit: net(cumFinal),
    netLow: net(cumLow),
    netHigh: net(cumHigh),
    roiPct: safeDiv(net(cumFinal), inp.spend) * 100,
  }
}
