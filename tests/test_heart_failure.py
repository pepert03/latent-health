"""Heart failure: beats, ECG and heart sound, Spanish cohort and patient record."""

import io
import wave
import zipfile
from datetime import date

import numpy as np
import pandas as pd
import pytest

from latenthealth import ejection, pulse
from latenthealth.assessment import ClinicalRecord, assess, describe
from latenthealth.home import HeartCheck, low_ef_prior, low_ef_probability
from latenthealth.music import COLUMNS, event_by, known_at, load_music
from latenthealth.wfdb import read_annotations, read_beats, read_header
from latenthealth.worklist import row_for

D0 = date(2026, 11, 16)

# --- Beat annotations in MIT format ---


def word(code: int, interval: int) -> bytes:
    return int((code << 10) | interval).to_bytes(2, "little")


def test_annotation_reader_handles_beats_skips_and_text(tmp_path):
    long_jump = 100_000
    data = b"".join([
        word(1, 100),  # normal beat at sample 100
        word(5, 90),  # premature ventricular beat
        word(59, 0), (long_jump >> 16).to_bytes(2, "little"), (long_jump & 0xFFFF).to_bytes(2, "little"),  # long skip
        word(1, 50),
        word(63, 3), b"abc\x00",  # 3-byte text, padded to 4
        word(14, 10),  # noise: not a beat
        word(1, 120),
        word(0, 0),
        word(1, 999),  # not read after the end
    ])  # fmt: skip
    path = tmp_path / "x.ecg"
    path.write_bytes(data)
    samples, codes = read_annotations(path)
    assert samples.tolist() == [100, 190, 100_240, 100_250, 100_370]
    assert codes.tolist() == [1, 5, 1, 14, 1]
    beats, normal = read_beats(path, 128.0)
    assert beats.tolist() == pytest.approx([100 / 128, 190 / 128, 100_240 / 128, 100_370 / 128])
    assert normal.tolist() == [True, False, True, True]


def test_header_gives_age_sex_and_class(tmp_path):
    path = tmp_path / "chf201.hea"
    path.write_text("chf201 0 128 0\n#Age: 55  Sex: M  NYHA class: III\n")
    info = read_header(path)
    assert info == {"record": "chf201", "fs": 128.0, "age": 55.0, "female": False, "nyha": 3}
    path.write_text("nsr001 0 128 0\n# Age: 64 Sex: F\n")
    info = read_header(path)
    assert info["female"] is True and info["nyha"] is None and info["age"] == 64.0


# --- Pulse features ---


def breathing(n=150, mean=0.85, depth=0.05, seed=0):
    """Healthy pulse: speeds up and slows down with breathing."""
    rng = np.random.default_rng(seed)
    return mean + depth * np.sin(2 * np.pi * np.arange(n) / 5.0) + 0.004 * rng.standard_normal(n)


def flat(n=150, mean=0.65, seed=0):
    """Fast, flat pulse."""
    return mean + 0.003 * np.random.default_rng(seed).standard_normal(n)


def test_pulse_features_add_rate_and_capacity():
    healthy, failing = pulse.pulse_features(breathing()), pulse.pulse_features(flat())
    assert set(pulse.FEATURES) <= set(healthy)
    assert healthy["rate"] == pytest.approx(60 / 0.85, rel=0.02) and failing["rate"] > 90
    assert healthy["dc"] > 0.01 > abs(failing["dc"])  # the healthy pulse slows with each breath
    assert healthy["ac"] < -0.01
    assert healthy["sdnn"] > 5 * failing["sdnn"]
    assert np.isnan(pulse.pulse_features([0.8, 0.8])["rate"])


def test_windows_cover_the_recording_and_drop_impossible_intervals():
    beats = np.cumsum(np.r_[np.full(300, 0.8), 5.0, np.full(300, 0.8)])
    starts = pulse.window_starts(beats, 60.0, 5)
    assert starts.size == 5 and starts[0] == beats[0] and starts[-1] == pytest.approx(beats[-1] - 60.0)
    rr = pulse.window_intervals(beats, beats[295], 60.0)
    assert rr.max() < 2.5 and rr.size > 50  # the 5 s pause does not count as an interval
    assert pulse.window_starts(beats[:10], 60.0, 5).size == 0


@pytest.mark.skipif(not pulse.available(), reason="model missing (scripts/fit_pulse_hf.py)")
def test_pulse_result_is_bounded_by_what_was_seen_in_spanish_patients():
    bundle = pulse._bundle()
    assert bundle["min_ratio"] < 1 < bundle["max_ratio"] < 5
    sick = pulse.classify_pulse([flat(seed=i) for i in range(7)])
    well = pulse.classify_pulse([breathing(seed=i) for i in range(7)])
    assert sick.usable and well.usable
    assert bundle["min_ratio"] <= well.likelihood_ratio <= sick.likelihood_ratio <= bundle["max_ratio"]
    assert sick.heart_rate > well.heart_rate
    assert not pulse.classify_pulse([[0.8, 0.8]]).usable


# --- Single-lead ECG and sound ---

FS, FS_SOUND = 500.0, 4000.0


def synthetic(rr=0.8, seconds=30.0, qrs=0.012, s1=0.05, s2=0.35, s1_gain=1.0, polarity=1.0, seed=0):
    """ECG with a Gaussian QRS and a T wave, and sound with two heart sounds after each beat."""
    rng = np.random.default_rng(seed)
    beats = np.arange(1.0, seconds - 1.0, rr)
    t = np.arange(int(seconds * FS)) / FS
    ecg = np.zeros_like(t)
    for b in beats:
        ecg += 1000.0 * np.exp(-0.5 * ((t - b) / qrs) ** 2) + 200.0 * np.exp(-0.5 * ((t - b - 0.28) / 0.04) ** 2)
    ecg = polarity * ecg + 5.0 * rng.standard_normal(t.size)
    ts = np.arange(int(seconds * FS_SOUND)) / FS_SOUND
    sound = 2.0 * rng.standard_normal(ts.size)
    for b in beats:
        for delay, gain in ((s1, s1_gain), (s2, 0.8)):
            burst = np.exp(-0.5 * ((ts - b - delay) / 0.015) ** 2)
            sound += 300.0 * gain * burst * np.sin(2 * np.pi * 90.0 * (ts - b - delay))
    return ecg, sound


def test_beats_are_aligned_whatever_the_polarity():
    for polarity in (1.0, -1.0):
        ecg, _ = synthetic(polarity=polarity)
        peaks, found = ejection.r_peaks(ejection.clean_ecg(ecg, FS), FS)
        assert found == polarity
        assert peaks.size == 35
        assert np.allclose(np.diff(peaks) / FS, 0.8, atol=0.004)


def test_sound_is_timed_against_the_qrs():
    ecg, sound = synthetic(s1=0.05, s2=0.35)
    late = ejection.recording_features(*(lambda e, s: (e, FS, s, FS_SOUND))(*synthetic(s1=0.10, s2=0.33, s1_gain=0.3)))
    normal = ejection.recording_features(ecg, FS, sound, FS_SOUND)
    assert normal["s1_time"] == pytest.approx(0.05, abs=0.012) and normal["s2_time"] == pytest.approx(0.35, abs=0.012)
    assert normal["systole"] == pytest.approx(0.30, abs=0.02)
    assert late["s1_time"] > normal["s1_time"] + 0.03  # the first heart sound is delayed
    assert late["systole"] < normal["systole"] - 0.04  # and systole shortens
    assert late["s1_s2"] < normal["s1_s2"] - 0.5  # and it is quieter than the second
    assert normal["rate"] == pytest.approx(75.0, rel=0.02)


def test_wide_qrs_is_measured_and_missing_sound_leaves_blanks():
    narrow = ejection.recording_features(synthetic(qrs=0.012)[0], FS)
    wide = ejection.recording_features(synthetic(qrs=0.035)[0], FS, profiles=True)
    assert wide["qrs_equivalent"] > 2 * narrow["qrs_equivalent"]
    assert wide["qrs_width"] > narrow["qrs_width"] and wide["qrs_slope"] < narrow["qrs_slope"]
    assert narrow["t_amplitude"] == pytest.approx(0.2, abs=0.06) and narrow["template_corr"] > 0.95
    assert all(np.isnan(narrow[name]) for name in ejection.SOUND)
    assert np.isfinite([wide[name] for name in ejection.ECG_PROFILE]).all()
    assert all(np.isnan(wide[name]) for name in ejection.SOUND_PROFILE)
    assert max(wide[name] for name in ejection.ECG_PROFILE) == pytest.approx(1.0, abs=0.2)  # the average beat is normalised


def wav_bytes(signal, fs) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(fs))
        handle.writeframes(np.clip(signal, -32000, 32000).astype("<i2").tobytes())
    return buffer.getvalue()


def test_archive_is_read_without_unpacking(tmp_path):
    path = tmp_path / "datos.zip"
    ecg, sound = synthetic(seconds=12.0)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("datos/fold_0_label.csv", "111_APEX,0.35\n111_LLSB,0.35\n222_APEX,0.62\n")
        archive.writestr("datos/fold_3_label.csv", "333_APEX,0.7\n")
        for subject in ("111", "222"):
            archive.writestr(f"datos/fold_0/{subject}_APEX_ECG.wav", wav_bytes(ecg, FS))
            archive.writestr(f"datos/fold_0/{subject}_APEX_PCG.wav", wav_bytes(sound, FS_SOUND))
        archive.writestr("datos/fold_0/111_LLSB_ECG.wav", wav_bytes(ecg, FS))
        archive.writestr("datos/fold_0/raro.wav", b"")
    labels = ejection.read_labels(path).set_index("subject")
    assert labels.loc["111"].tolist() == [0.35, 0] and labels.loc["333"].tolist() == [0.7, 3] and len(labels) == 3
    names = ejection.recording_names(path)
    assert set(names) == {("111", "APEX"), ("111", "LLSB"), ("222", "APEX")}
    table = ejection.features_from_zip(path, subjects=["111"])
    assert table[["subject", "site"]].values.tolist() == [["111", "APEX"], ["111", "LLSB"]]
    assert np.isfinite(table.loc[0, "s1_time"]) and np.isnan(table.loc[1, "s1_time"])  # the second has no sound
    fs, signal = ejection.read_wav(wav_bytes(ecg, FS))
    assert fs == FS and signal.size == ecg.size


@pytest.mark.skipif(not ejection.available(), reason="model missing (scripts/fit_ejection.py)")
def test_model_gives_a_bounded_result_for_each_level_of_equipment():
    bundle = ejection._bundle()
    assert set(bundle["models"]) == {"pulso", "ecg", "sonido"}
    assert bundle["models"]["pulso"]["auc"] < bundle["models"]["ecg"]["auc"] < bundle["models"]["sonido"]["auc"]
    recording = ejection.recording_features(*(lambda e, s: (e, FS, s, FS_SOUND))(*synthetic()), profiles=True)
    for tier in bundle["models"]:
        result = ejection.classify([recording, recording], tier)
        assert result.usable and 0 < result.probability < 1
        assert 1 / bundle["max_ratio"] <= result.likelihood_ratio <= bundle["max_ratio"]
    empty = ejection.classify([ejection.recording_features(np.zeros(2000), FS)])
    assert not empty.usable and empty.likelihood_ratio == 1.0
    check = ejection.check_from_recordings(D0, [recording], "ecg")
    assert check.source == "ecg" and check.likelihood_ratio == pytest.approx(ejection.classify([recording], "ecg").likelihood_ratio)


# --- Probability of low ejection fraction and patient record ---


def test_recordings_are_averaged_and_only_the_best_source_counts():
    prior = low_ef_prior(70)
    assert prior == pytest.approx(0.5 * 0.018 / (1 - 0.5 * 0.018))
    assert low_ef_prior(70, coronary=True) > 5 * prior > 5 * low_ef_prior(40)
    one = low_ef_probability([HeartCheck(D0, 8.0)], 70)
    odds = prior / (1 - prior) * 8.0
    assert one == pytest.approx(odds / (1 + odds))
    assert low_ef_probability([HeartCheck(D0, 8.0), HeartCheck(D0, 8.0)], 70) == pytest.approx(one)  # it is the same heart
    assert low_ef_probability([HeartCheck(D0, 8.0), HeartCheck(D0, 2.0)], 70) < one
    mixed = [HeartCheck(D0, 8.0, "ecg y sonido"), HeartCheck(D0, 0.5, "pulso")]
    assert low_ef_probability(mixed, 70) == pytest.approx(one)
    assert low_ef_probability([HeartCheck(D0, 2.0, "pulso")], 70) > prior
    assert low_ef_probability([], 70) == pytest.approx(prior)


def test_a_suspicious_recording_asks_for_an_echocardiogram():
    base = dict(age=71, female=False, bmi=29.0, hypertension=True, bp_meds=True, sbp=138.0)
    plain = assess(ClinicalRecord(**base), as_of=D0)
    assert plain.p_low_ef is None and "ecocardiograma" not in plain.finding_by_test
    flagged = assess(ClinicalRecord(**base, heart_checks=[HeartCheck(D0, 10.0, "ecg y sonido")]), as_of=D0)
    assert flagged.p_low_ef == pytest.approx(low_ef_probability([HeartCheck(D0, 10.0)], 71))
    assert flagged.heart_failure == "to rule out"
    assert any(r.test == "Echocardiogram" for r in flagged.recommendations)
    assert flagged.finding_by_test["ecocardiograma"] == pytest.approx(flagged.p_low_ef)
    assert flagged.p_new_finding > plain.p_new_finding
    assert "Low ejection fraction" in describe(flagged)
    assert "echocardiogram" in " ".join(row_for("p1", flagged).reasons)
    clean = assess(ClinicalRecord(**base, heart_checks=[HeartCheck(D0, 0.3, "ecg y sonido")]), as_of=D0)
    assert clean.p_low_ef < low_ef_prior(71) and not any(r.test == "Echocardiogram" for r in clean.recommendations)
    known = assess(ClinicalRecord(**base, heart_failure=True, heart_checks=[HeartCheck(D0, 10.0)]), as_of=D0)
    assert known.p_low_ef is None and known.heart_failure == "diagnosed"


# --- Spanish MUSIC cohort ---


def test_music_table_is_cleaned(tmp_path):
    header = []
    for prefix in COLUMNS:
        if prefix == "Average RR (ms).1":
            header.append("Average RR  (ms)")  # repeated, with different spacing: the Holter one
        elif prefix == "Average RR (ms)":
            header.append(prefix)
        elif prefix == "Creatinine":
            header.append("Creatinine (?mol/L)")
        else:
            header.append(prefix + " (x)")
    rows = []
    for patient, days, exit_code, cause, pr, rr in (("P1", 2000, "", 0, 160, 1111), ("P2", 400, 3, 6, 999, 600), ("P3", 300, 2, 0, 180, 800), ("P4", 900, 3, 1, 150, 999)):
        values = dict.fromkeys(COLUMNS, "1")
        values.update({"Patient ID": patient, "Follow-up period from enrollment": days, "Exit of the study": exit_code, "Cause of death": cause,
                       "Age": 70, "PR interval": pr, "QRS duration": 120, "QT corrected": 440, "Average RR (ms)": rr, "Average RR (ms).1": 850,
                       "Body Mass Index": "31,2", "ECG rhythm": 1 if patient == "P2" else 0, "HF etiology": 2, "Prior implantable device": 5})  # fmt: skip
        rows.append(";".join(str(values[k]) for k in COLUMNS))
    (tmp_path / "subject-info.csv").write_text(";".join(header) + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    d = load_music(tmp_path).set_index("patient")
    assert d.loc["P1", "bmi"] == 31.2 and d.loc["P1", "rr_holter"] == 850
    assert np.isnan(d.loc["P2", "pr"]) and d.loc["P1", "pr"] == 160  # 999 means "not measurable"
    assert d.loc["P1", "heart_rate"] == pytest.approx(54.0, abs=0.1) and d.loc["P4", "heart_rate"] == pytest.approx(60.06, abs=0.01)
    assert d.irregular.tolist() == [0.0, 1.0, 0.0, 0.0] and d.ischemic.eq(1).all() and d.device.eq(1).all()
    assert d.death.tolist() == [False, True, False, True]
    assert d.pump_death.tolist() == [False, True, False, False] and d.cardiac_death.tolist() == [False, True, False, False]
    d = d.reset_index()
    assert known_at(d, 3.0).tolist() == [True, True, False, True]  # the patient transplanted at one year does not count at three years
    assert event_by(d, 2.0).tolist() == [False, True, False, False]
    assert event_by(d, 3.0).tolist() == [False, True, False, True]


def test_music_loader_complains_about_a_missing_column(tmp_path):
    pd.DataFrame({"Patient ID": ["P1"]}).to_csv(tmp_path / "subject-info.csv", sep=";", index=False)
    with pytest.raises(KeyError):
        load_music(tmp_path)
