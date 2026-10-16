// AUTO-GENERATED from pythermalcomfort 4.6.0 models/utci.py (_utci_optimized).
// Do not edit by hand. Inputs: tdb [C], v [m/s at 10 m], dtr = tr - tdb [C], pa [kPa].
#pragma once
static double utci_poly(double tdb, double v, double dtr, double pa) {
  return tdb
    + 0.607562052
    + (-0.0227712343) * tdb
    + (8.06470249 * 1e-4) * tdb * tdb
    + (-1.54271372 * 1e-4) * tdb * tdb * tdb
    + (-3.24651735 * 1e-6) * tdb * tdb * tdb * tdb
    + (7.32602852 * 1e-8) * tdb * tdb * tdb * tdb * tdb
    + (1.35959073 * 1e-9) * tdb * tdb * tdb * tdb * tdb * tdb
    + (-2.25836520) * v
    + 0.0880326035 * tdb * v
    + 0.00216844454 * tdb * tdb * v
    + (-1.53347087 * 1e-5) * tdb * tdb * tdb * v
    + (-5.72983704 * 1e-7) * tdb * tdb * tdb * tdb * v
    + (-2.55090145 * 1e-9) * tdb * tdb * tdb * tdb * tdb * v
    + (-0.751269505) * v * v
    + (-0.00408350271) * tdb * v * v
    + (-5.21670675 * 1e-5) * tdb * tdb * v * v
    + (1.94544667 * 1e-6) * tdb * tdb * tdb * v * v
    + (1.14099531 * 1e-8) * tdb * tdb * tdb * tdb * v * v
    + 0.158137256 * v * v * v
    + (-6.57263143 * 1e-5) * tdb * v * v * v
    + (2.22697524 * 1e-7) * tdb * tdb * v * v * v
    + (-4.16117031 * 1e-8) * tdb * tdb * tdb * v * v * v
    + (-0.0127762753) * v * v * v * v
    + (9.66891875 * 1e-6) * tdb * v * v * v * v
    + (2.52785852 * 1e-9) * tdb * tdb * v * v * v * v
    + (4.56306672 * 1e-4) * v * v * v * v * v
    + (-1.74202546 * 1e-7) * tdb * v * v * v * v * v
    + (-5.91491269 * 1e-6) * v * v * v * v * v * v
    + 0.398374029 * dtr
    + (1.83945314 * 1e-4) * tdb * dtr
    + (-1.73754510 * 1e-4) * tdb * tdb * dtr
    + (-7.60781159 * 1e-7) * tdb * tdb * tdb * dtr
    + (3.77830287 * 1e-8) * tdb * tdb * tdb * tdb * dtr
    + (5.43079673 * 1e-10) * tdb * tdb * tdb * tdb * tdb * dtr
    + (-0.0200518269) * v * dtr
    + (8.92859837 * 1e-4) * tdb * v * dtr
    + (3.45433048 * 1e-6) * tdb * tdb * v * dtr
    + (-3.77925774 * 1e-7) * tdb * tdb * tdb * v * dtr
    + (-1.69699377 * 1e-9) * tdb * tdb * tdb * tdb * v * dtr
    + (1.69992415 * 1e-4) * v * v * dtr
    + (-4.99204314 * 1e-5) * tdb * v * v * dtr
    + (2.47417178 * 1e-7) * tdb * tdb * v * v * dtr
    + (1.07596466 * 1e-8) * tdb * tdb * tdb * v * v * dtr
    + (8.49242932 * 1e-5) * v * v * v * dtr
    + (1.35191328 * 1e-6) * tdb * v * v * v * dtr
    + (-6.21531254 * 1e-9) * tdb * tdb * v * v * v * dtr
    + (-4.99410301 * 1e-6) * v * v * v * v * dtr
    + (-1.89489258 * 1e-8) * tdb * v * v * v * v * dtr
    + (8.15300114 * 1e-8) * v * v * v * v * v * dtr
    + (7.55043090 * 1e-4) * dtr * dtr
    + (-5.65095215 * 1e-5) * tdb * dtr * dtr
    + (-4.52166564 * 1e-7) * tdb * tdb * dtr * dtr
    + (2.46688878 * 1e-8) * tdb * tdb * tdb * dtr * dtr
    + (2.42674348 * 1e-10) * tdb * tdb * tdb * tdb * dtr * dtr
    + (1.54547250 * 1e-4) * v * dtr * dtr
    + (5.24110970 * 1e-6) * tdb * v * dtr * dtr
    + (-8.75874982 * 1e-8) * tdb * tdb * v * dtr * dtr
    + (-1.50743064 * 1e-9) * tdb * tdb * tdb * v * dtr * dtr
    + (-1.56236307 * 1e-5) * v * v * dtr * dtr
    + (-1.33895614 * 1e-7) * tdb * v * v * dtr * dtr
    + (2.49709824 * 1e-9) * tdb * tdb * v * v * dtr * dtr
    + (6.51711721 * 1e-7) * v * v * v * dtr * dtr
    + (1.94960053 * 1e-9) * tdb * v * v * v * dtr * dtr
    + (-1.00361113 * 1e-8) * v * v * v * v * dtr * dtr
    + (-1.21206673 * 1e-5) * dtr * dtr * dtr
    + (-2.18203660 * 1e-7) * tdb * dtr * dtr * dtr
    + (7.51269482 * 1e-9) * tdb * tdb * dtr * dtr * dtr
    + (9.79063848 * 1e-11) * tdb * tdb * tdb * dtr * dtr * dtr
    + (1.25006734 * 1e-6) * v * dtr * dtr * dtr
    + (-1.81584736 * 1e-9) * tdb * v * dtr * dtr * dtr
    + (-3.52197671 * 1e-10) * tdb * tdb * v * dtr * dtr * dtr
    + (-3.36514630 * 1e-8) * v * v * dtr * dtr * dtr
    + (1.35908359 * 1e-10) * tdb * v * v * dtr * dtr * dtr
    + (4.17032620 * 1e-10) * v * v * v * dtr * dtr * dtr
    + (-1.30369025 * 1e-9) * dtr * dtr * dtr * dtr
    + (4.13908461 * 1e-10) * tdb * dtr * dtr * dtr * dtr
    + (9.22652254 * 1e-12) * tdb * tdb * dtr * dtr * dtr * dtr
    + (-5.08220384 * 1e-9) * v * dtr * dtr * dtr * dtr
    + (-2.24730961 * 1e-11) * tdb * v * dtr * dtr * dtr * dtr
    + (1.17139133 * 1e-10) * v * v * dtr * dtr * dtr * dtr
    + (6.62154879 * 1e-10) * dtr * dtr * dtr * dtr * dtr
    + (4.03863260 * 1e-13) * tdb * dtr * dtr * dtr * dtr * dtr
    + (1.95087203 * 1e-12) * v * dtr * dtr * dtr * dtr * dtr
    + (-4.73602469 * 1e-12) * dtr * dtr * dtr * dtr * dtr * dtr
    + 5.12733497 * pa
    + (-0.312788561) * tdb * pa
    + (-0.0196701861) * tdb * tdb * pa
    + (9.99690870 * 1e-4) * tdb * tdb * tdb * pa
    + (9.51738512 * 1e-6) * tdb * tdb * tdb * tdb * pa
    + (-4.66426341 * 1e-7) * tdb * tdb * tdb * tdb * tdb * pa
    + 0.548050612 * v * pa
    + (-0.00330552823) * tdb * v * pa
    + (-0.00164119440) * tdb * tdb * v * pa
    + (-5.16670694 * 1e-6) * tdb * tdb * tdb * v * pa
    + (9.52692432 * 1e-7) * tdb * tdb * tdb * tdb * v * pa
    + (-0.0429223622) * v * v * pa
    + 0.00500845667 * tdb * v * v * pa
    + (1.00601257 * 1e-6) * tdb * tdb * v * v * pa
    + (-1.81748644 * 1e-6) * tdb * tdb * tdb * v * v * pa
    + (-1.25813502 * 1e-3) * v * v * v * pa
    + (-1.79330391 * 1e-4) * tdb * v * v * v * pa
    + (2.34994441 * 1e-6) * tdb * tdb * v * v * v * pa
    + (1.29735808 * 1e-4) * v * v * v * v * pa
    + (1.29064870 * 1e-6) * tdb * v * v * v * v * pa
    + (-2.28558686 * 1e-6) * v * v * v * v * v * pa
    + (-0.0369476348) * dtr * pa
    + 0.00162325322 * tdb * dtr * pa
    + (-3.14279680 * 1e-5) * tdb * tdb * dtr * pa
    + (2.59835559 * 1e-6) * tdb * tdb * tdb * dtr * pa
    + (-4.77136523 * 1e-8) * tdb * tdb * tdb * tdb * dtr * pa
    + (8.64203390 * 1e-3) * v * dtr * pa
    + (-6.87405181 * 1e-4) * tdb * v * dtr * pa
    + (-9.13863872 * 1e-6) * tdb * tdb * v * dtr * pa
    + (5.15916806 * 1e-7) * tdb * tdb * tdb * v * dtr * pa
    + (-3.59217476 * 1e-5) * v * v * dtr * pa
    + (3.28696511 * 1e-5) * tdb * v * v * dtr * pa
    + (-7.10542454 * 1e-7) * tdb * tdb * v * v * dtr * pa
    + (-1.24382300 * 1e-5) * v * v * v * dtr * pa
    + (-7.38584400 * 1e-9) * tdb * v * v * v * dtr * pa
    + (2.20609296 * 1e-7) * v * v * v * v * dtr * pa
    + (-7.32469180 * 1e-4) * dtr * dtr * pa
    + (-1.87381964 * 1e-5) * tdb * dtr * dtr * pa
    + (4.80925239 * 1e-6) * tdb * tdb * dtr * dtr * pa
    + (-8.75492040 * 1e-8) * tdb * tdb * tdb * dtr * dtr * pa
    + (2.77862930 * 1e-5) * v * dtr * dtr * pa
    + (-5.06004592 * 1e-6) * tdb * v * dtr * dtr * pa
    + (1.14325367 * 1e-7) * tdb * tdb * v * dtr * dtr * pa
    + (2.53016723 * 1e-6) * v * v * dtr * dtr * pa
    + (-1.72857035 * 1e-8) * tdb * v * v * dtr * dtr * pa
    + (-3.95079398 * 1e-8) * v * v * v * dtr * dtr * pa
    + (-3.59413173 * 1e-7) * dtr * dtr * dtr * pa
    + (7.04388046 * 1e-7) * tdb * dtr * dtr * dtr * pa
    + (-1.89309167 * 1e-8) * tdb * tdb * dtr * dtr * dtr * pa
    + (-4.79768731 * 1e-7) * v * dtr * dtr * dtr * pa
    + (7.96079978 * 1e-9) * tdb * v * dtr * dtr * dtr * pa
    + (1.62897058 * 1e-9) * v * v * dtr * dtr * dtr * pa
    + (3.94367674 * 1e-8) * dtr * dtr * dtr * dtr * pa
    + (-1.18566247 * 1e-9) * tdb * dtr * dtr * dtr * dtr * pa
    + (3.34678041 * 1e-10) * v * dtr * dtr * dtr * dtr * pa
    + (-1.15606447 * 1e-10) * dtr * dtr * dtr * dtr * dtr * pa
    + (-2.80626406) * pa * pa
    + 0.548712484 * tdb * pa * pa
    + (-0.00399428410) * tdb * tdb * pa * pa
    + (-9.54009191 * 1e-4) * tdb * tdb * tdb * pa * pa
    + (1.93090978 * 1e-5) * tdb * tdb * tdb * tdb * pa * pa
    + (-0.308806365) * v * pa * pa
    + 0.0116952364 * tdb * v * pa * pa
    + (4.95271903 * 1e-4) * tdb * tdb * v * pa * pa
    + (-1.90710882 * 1e-5) * tdb * tdb * tdb * v * pa * pa
    + 0.00210787756 * v * v * pa * pa
    + (-6.98445738 * 1e-4) * tdb * v * v * pa * pa
    + (2.30109073 * 1e-5) * tdb * tdb * v * v * pa * pa
    + (4.17856590 * 1e-4) * v * v * v * pa * pa
    + (-1.27043871 * 1e-5) * tdb * v * v * v * pa * pa
    + (-3.04620472 * 1e-6) * v * v * v * v * pa * pa
    + 0.0514507424 * dtr * pa * pa
    + (-0.00432510997) * tdb * dtr * pa * pa
    + (8.99281156 * 1e-5) * tdb * tdb * dtr * pa * pa
    + (-7.14663943 * 1e-7) * tdb * tdb * tdb * dtr * pa * pa
    + (-2.66016305 * 1e-4) * v * dtr * pa * pa
    + (2.63789586 * 1e-4) * tdb * v * dtr * pa * pa
    + (-7.01199003 * 1e-6) * tdb * tdb * v * dtr * pa * pa
    + (-1.06823306 * 1e-4) * v * v * dtr * pa * pa
    + (3.61341136 * 1e-6) * tdb * v * v * dtr * pa * pa
    + (2.29748967 * 1e-7) * v * v * v * dtr * pa * pa
    + (3.04788893 * 1e-4) * dtr * dtr * pa * pa
    + (-6.42070836 * 1e-5) * tdb * dtr * dtr * pa * pa
    + (1.16257971 * 1e-6) * tdb * tdb * dtr * dtr * pa * pa
    + (7.68023384 * 1e-6) * v * dtr * dtr * pa * pa
    + (-5.47446896 * 1e-7) * tdb * v * dtr * dtr * pa * pa
    + (-3.59937910 * 1e-8) * v * v * dtr * dtr * pa * pa
    + (-4.36497725 * 1e-6) * dtr * dtr * dtr * pa * pa
    + (1.68737969 * 1e-7) * tdb * dtr * dtr * dtr * pa * pa
    + (2.67489271 * 1e-8) * v * dtr * dtr * dtr * pa * pa
    + (3.23926897 * 1e-9) * dtr * dtr * dtr * dtr * pa * pa
    + (-0.0353874123) * pa * pa * pa
    + (-0.221201190) * tdb * pa * pa * pa
    + 0.0155126038 * tdb * tdb * pa * pa * pa
    + (-2.63917279 * 1e-4) * tdb * tdb * tdb * pa * pa * pa
    + 0.0453433455 * v * pa * pa * pa
    + (-0.00432943862) * tdb * v * pa * pa * pa
    + (1.45389826 * 1e-4) * tdb * tdb * v * pa * pa * pa
    + (2.17508610 * 1e-4) * v * v * pa * pa * pa
    + (-6.66724702 * 1e-5) * tdb * v * v * pa * pa * pa
    + (3.33217140 * 1e-5) * v * v * v * pa * pa * pa
    + (-0.00226921615) * dtr * pa * pa * pa
    + (3.80261982 * 1e-4) * tdb * dtr * pa * pa * pa
    + (-5.45314314 * 1e-9) * tdb * tdb * dtr * pa * pa * pa
    + (-7.96355448 * 1e-4) * v * dtr * pa * pa * pa
    + (2.53458034 * 1e-5) * tdb * v * dtr * pa * pa * pa
    + (-6.31223658 * 1e-6) * v * v * dtr * pa * pa * pa
    + (3.02122035 * 1e-4) * dtr * dtr * pa * pa * pa
    + (-4.77403547 * 1e-6) * tdb * dtr * dtr * pa * pa * pa
    + (1.73825715 * 1e-6) * v * dtr * dtr * pa * pa * pa
    + (-4.09087898 * 1e-7) * dtr * dtr * dtr * pa * pa * pa
    + 0.614155345 * pa * pa * pa * pa
    + (-0.0616755931) * tdb * pa * pa * pa * pa
    + 0.00133374846 * tdb * tdb * pa * pa * pa * pa
    + 0.00355375387 * v * pa * pa * pa * pa
    + (-5.13027851 * 1e-4) * tdb * v * pa * pa * pa * pa
    + (1.02449757 * 1e-4) * v * v * pa * pa * pa * pa
    + (-0.00148526421) * dtr * pa * pa * pa * pa
    + (-4.11469183 * 1e-5) * tdb * dtr * pa * pa * pa * pa
    + (-6.80434415 * 1e-6) * v * dtr * pa * pa * pa * pa
    + (-9.77675906 * 1e-6) * dtr * dtr * pa * pa * pa * pa
    + 0.0882773108 * pa * pa * pa * pa * pa
    + (-0.00301859306) * tdb * pa * pa * pa * pa * pa
    + 0.00104452989 * v * pa * pa * pa * pa * pa
    + (2.47090539 * 1e-4) * dtr * pa * pa * pa * pa * pa
    + 0.00148348065 * pa * pa * pa * pa * pa * pa;
}
