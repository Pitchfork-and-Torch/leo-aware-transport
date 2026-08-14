# Related work (conceptual comparison)

LeoAware is a **research prototype**, not a bit-exact clone of any production or published CCA. The table is for orientation.

| Approach | Core idea | Cooperation needed | LeoAware relationship |
|----------|-----------|--------------------|------------------------|
| **CUBIC** | Loss-driven cubic window | None | Baseline; fails on non-congestive LEO loss |
| **BBR family** | Max BW + min RTT model | None | Baseline; stale min-RTT across LEO epochs hurts BDP |
| **LeoCC-style** | Endpoint signals (ACK IA / RTT patterns) for LEO | Low | LeoAware detection is in this family |
| **SaTCP / StarQUIC freeze** | Freeze / protect state across known freezes | Medium (event awareness) | LeoAware REPROBE is a soft alternative to hard freeze |
| **OrbCC-class** | In-network / orbital assists | High | Future path; LeoAware `on_path_hint` is the hook |
| **Multipath QUIC** | Schedule across paths | Medium | Stretch; ISL flag is a seed only |
| **Zhao/Pan Starlink traces** | IRTT + iPerf3 Cubic, Victoria→Seattle PoP (PIMRC 2023 / Zenodo 10.5281/zenodo.10020034) | None (measurement) | Research-era `zhao_zenodo23` ingest; not a CCA lock |

## Design choice summary

LeoAware prioritizes:

1. **Deployability** - pure endpoint logic first (Cloudflare edge / quiche).
2. **Correct sample lifetime** - invalidate BW and min-RTT after path change.
3. **Loss taxonomy** - mobility vs congestion before reducing cwnd.

It does **not** claim superiority on all terrestrial paths or bit-exact BBR competition; the suite includes a terrestrial control for sanity.
