// habub_utci.h — UTCI calculation for the Habub node (local display only).
// The server remains the authoritative source; this mirrors pythermalcomfort 4.6.0.
#pragma once
#include <math.h>
#include "utci_poly.h"

// Saturation vapour pressure [hPa] — same formula as pythermalcomfort.utci (exponential()).
static double habub_es_hpa(double tdb) {
  const double g[7] = {-2836.5744, -6028.076559, 19.54263612, -0.02737830188,
                       0.000016261698, 7.0229056e-10, -1.8680009e-13};
  double tk = tdb + 273.15;
  double es = 2.7150305 * log(tk);
  for (int i = 0; i < 7; i++) es += g[i] * pow(tk, i - 2);
  return exp(es) * 0.01;
}

// Log wind profile (pythermalcomfort.environment.scale_wind_speed_log), measured
// at height z_meas [m] -> 10 m. z0 = roughness length [m], d = displacement [m].
static double habub_wind_to_10m(double v_meas, double z_meas, double z0, double d) {
  return v_meas * log((10.0 - d) / z0) / log((z_meas - d) / z0);
}

// Returns UTCI [C]; NAN if tdb or tr-tdb out of the model range.
// v10 must already be clamped to [0.5, 17].
static double habub_utci(double tdb, double tr, double v10, double rh) {
  if (tdb <= -50.0 || tdb >= 50.0) return NAN;
  double dtr = tr - tdb;
  if (dtr <= -30.0 || dtr >= 70.0) return NAN;
  double pa = habub_es_hpa(tdb) * (rh / 100.0) / 10.0;  // kPa
  return utci_poly(tdb, v10, dtr, pa);
}

// Stress category index 0..9 (thresholds from pythermalcomfort; the value is first
// rounded to 0.1 C and each bin includes its upper edge, as in the library).
static int habub_utci_category(double u) {
  u = round(u * 10.0) / 10.0;
  const double th[9] = {-40, -27, -13, 0, 9, 26, 32, 38, 46};
  for (int i = 0; i < 9; i++) if (u <= th[i]) return i;
  return 9;
}
