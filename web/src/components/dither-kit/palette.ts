// Shared seed palette for the dither chart family. Mirrors the seeds in
// `dither-chart.tsx` so a series rendered through the composable engine reads
// with the exact same fill / line / star hues as the legacy sparkline.

export type Rgb = [number, number, number]

export type DitherColor =
  | "ink"
  | "green"
  | "blue"
  | "purple"
  | "pink"
  | "orange"
  | "amber"
  | "red"
  | "grey"

export type Seed = { fill: Rgb; line: Rgb; star: Rgb }

// CareLoop: fills deepened to read on a white card (the engine paints with the
// fill colour alone and varies opacity), plus `ink` for the black accent and
// `amber` for the REVIEW triage level.
export const PALETTE: Record<DitherColor, Seed> = {
  ink: { fill: [24, 24, 27], line: [10, 10, 10], star: [63, 63, 70] },
  green: { fill: [22, 150, 80], line: [21, 128, 61], star: [74, 222, 128] },
  blue: { fill: [37, 99, 235], line: [29, 78, 216], star: [147, 197, 253] },
  purple: { fill: [124, 58, 237], line: [109, 40, 217], star: [196, 181, 253] },
  pink: { fill: [219, 39, 119], line: [190, 24, 93], star: [249, 168, 212] },
  orange: { fill: [234, 88, 12], line: [194, 65, 12], star: [253, 186, 116] },
  amber: { fill: [202, 138, 4], line: [161, 98, 7], star: [252, 211, 77] },
  red: { fill: [220, 38, 38], line: [185, 28, 28], star: [252, 165, 165] },
  // No-data: a muted grey so empty metrics read as "nothing here".
  grey: { fill: [113, 113, 122], line: [82, 82, 91], star: [161, 161, 170] },
}

export const rgb = ([r, g, b]: Rgb, k = 1, a = 1) =>
  `rgba(${Math.round(r * k)},${Math.round(g * k)},${Math.round(b * k)},${a})`

export const seedOfColor = (color: DitherColor): Seed => PALETTE[color]

export const isDitherColor = (value: unknown): value is DitherColor =>
  typeof value === "string" && value in PALETTE
