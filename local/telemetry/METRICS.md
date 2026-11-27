Here is the complete table of all **19** behavioral & webcam metrics (plus the `valid_frame_ratio` quality gate):

| # | Metric | Currently in Rules/Grafana? | Direction Under Fatigue | What It Evaluates |
| :-: | :--- | :---: | :--- | :--- |
| 1 | **`key_flight_ms`** | ✅ Yes *(anchored)* | **↑ Longer** | **Mental fatigue & circadian sleepiness** — primary typing slowdown marker (*de Jong et al. 2020*; *Althoff et al. 2017*). |
| 2 | **`backspace_rate`** | ✅ Yes *(anchored)* | **↑ Higher** | **Early mental fatigue & stress** — rises in morning compensation (*de Jong et al. 2020*) and spikes with rushed typing under stress. |
| 3 | **`key_hold_ms`** | Stored only | **↑ Longer** | **Fine motor fatigue** — finger press-to-release dwell lengthens (*Pimenta et al. 2013*). |
| 4 | **`key_pause_rate`** | Stored only | **↑ Higher** | **Cognitive hesitation** — more `>2s` mid-typing pauses reflect slower thought/language retrieval. |
| 5 | **`mouse_velocity_px_per_sec`** | ✅ Yes *(anchored)* | **↓ Lower** | **Mental fatigue & cognitive load** — decreased in 90% of fatigued users (*Pimenta et al. 2013*). |
| 6 | **`mouse_acceleration_px_per_sec2`** | Stored only | **↓ Lower** | **Mental fatigue** — drops alongside velocity as motor control degrades (*Pimenta et al. 2013*). |
| 7 | **`mouse_click_latency_ms`** | Stored only | **↑ Longer** | **Circadian sleepiness & sleep debt** — pre-click hesitation slows after short sleep (*Althoff et al. 2017*). |
| 8 | **`mouse_clicks_per_min`** | Stored only | **↓ Lower** | **Activity / engagement** — separates active editing/browsing from passive reading. |
| 9 | **`window_focus_duration_s`** | ✅ Yes *(anchored)* | **↓ Shorter** | **Sleep debt & attentional fragmentation** — shorter focus after poor sleep (*Mark et al., CHI 2016*). |
| 10 | **`window_switches_per_min`** | ✅ Yes *(anchored)* | **↑ Higher** | **Distraction & fragmentation** — rapid app switching; paired with sharp typing = external distraction. |
| 11 | **`webcam_perclos`** | ✅ Yes *(> 0.15)* | **↑ Higher** | **Sleepiness & drowsiness** — gold-standard non-contact ocular drowsiness metric (*PMC10108649*). |
| 12 | **`webcam_microsleeps`** | ✅ Yes *(≥ 1)* | **↑ Count** | **Severe drowsiness** — eye closures `> 500 ms` (*PMC10108649*). |
| 13 | **`webcam_ear_variance`** | Stored only | **↑ Higher** | **Drowsiness** — #1 predictive feature (~41% weight) on realistic webcams (*UTA-RLDD 2025*). |
| 14 | **`webcam_blink_duration_ms`** | Stored only | **↑ Longer** | **Drowsiness & early microsleeps** — #2 predictive feature (~30% weight, *UTA-RLDD 2025*). |
| 15 | **`webcam_blink_rate_per_min`** | Stored only | **↓ Load / ↑ Fatigue** | **Visual load vs. fatigue** — drops to ~9–17/min under intense focus, rebounds under fatigue. |
| 16 | **`webcam_mar`** | Stored only | **↑ Higher** | **Sleepiness** — Mouth Aspect Ratio detects yawning. |
| 17 | **`webcam_lid_tightening`** | Stored only | **↓ Smaller** | **Vigilance loss** — correlated `r = 0.89` with PVT slowing (*Kong et al. 2020*). |
| 18 | **`webcam_head_pitch_variance`** | Stored only | **↑ Higher** | **Severe drowsiness / nodding** — correlated `r = 0.84` with vigilance lapses (*Kong et al. 2020*). |
| 19 | **`webcam_rppg_hr_bpm`** | Stored only | **↑ Stress / ↓ Rest** | **Autonomic arousal** — 30s forehead HR helps separate acute stress from calm drowsiness. |
| — | *`webcam_valid_frame_ratio`* | *Internal gate* | *`< 0.50` = withhold* | *Quality guard — withholds webcam metrics when lighting is dim, no face, or extreme yaw.* |
