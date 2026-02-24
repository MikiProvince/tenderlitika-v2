import os
import json
import time
import statistics
import requests
from typing import Any, Dict, List, Tuple

from tools.tender_corpus_generator import generate_tender

API_BASE = os.getenv("TL_API_BASE", "http://127.0.0.1:8000")
API_KEY = os.getenv("TL_API_KEY", "")  # если у тебя auth по API key
N = int(os.getenv("TL_N", "30"))

def _hdrs() -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    # ⚠️ ВАЖНО: проверь, как у тебя называется хедер ключа:
    # часто это "x-api-key" или "X-API-Key"
    if API_KEY:
        h["x-api-key"] = API_KEY
    return h

def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) else None

def _bool(x: Any) -> bool | None:
    return bool(x) if isinstance(x, bool) else None

def compare(extracted: Dict[str, Any], truth: Dict[str, Any]) -> Dict[str, Any]:
    """
    Мини-оценка качества:
    - nmck (точность ±1%)
    - execution_days exact
    - payment_terms_days exact
    - ловушки exact
    """
    result = {"ok": True, "checks": []}

    # nmck tolerance
    nmck = _num(extracted.get("nmck"))
    t_nmck = _num(truth.get("nmck"))
    if nmck is None or t_nmck is None:
        result["ok"] = False
        result["checks"].append(("nmck", False, nmck, t_nmck))
    else:
        tol = 0.01 * t_nmck
        good = abs(nmck - t_nmck) <= tol
        result["ok"] = result["ok"] and good
        result["checks"].append(("nmck", good, nmck, t_nmck))

    for k in ["execution_days", "payment_terms_days"]:
        v = extracted.get(k)
        tv = truth.get(k)
        good = (isinstance(v, (int, float)) and int(v) == int(tv))
        result["ok"] = result["ok"] and good
        result["checks"].append((k, good, v, tv))

    for k in ["payment_after_full_delivery", "delivery_by_customer_requests", "supplier_must_hold_stock", "has_vague_acceptance_terms"]:
        v = extracted.get(k)
        tv = truth.get(k)
        good = (isinstance(v, bool) and v == tv)
        result["ok"] = result["ok"] and good
        result["checks"].append((k, good, v, tv))

    return result

def main():
    url = f"{API_BASE}/analyze"
    print(f"API: {url}")
    print(f"N: {N}")
    if API_KEY:
        print("Auth: x-api-key is set ✅")
    else:
        print("Auth: TL_API_KEY not set (ok if your backend allows it)")

    oks: List[bool] = []
    risk_scores: List[int] = []
    safe_costs: List[float] = []
    per_mode = {"safe": [], "trap": [], "hidden_loss": []}

    failures: List[Dict[str, Any]] = []

    for i in range(N):
        mode = ["safe", "trap", "hidden_loss"][i % 3]
        text, truth = generate_tender(mode)

        # для финансовой части теста:
        # себестоимость сделаем как % от НМЦК
        nmck = truth["nmck"]
        cost_price = round(nmck * (0.84 if mode == "safe" else 0.90), 2)
        margin = 12.0

        payload = {
            "text": text,
            "cost_price": cost_price,
            "planned_margin_percent": margin,
        }

        try:
            r = requests.post(url, headers=_hdrs(), data=json.dumps(payload), timeout=60)
            if r.status_code != 200:
                failures.append({
                    "i": i, "mode": mode,
                    "status": r.status_code,
                    "body": r.text[:500],
                })
                oks.append(False)
                per_mode[mode].append(False)
                continue

            body = r.json()
            extracted = body.get("extracted_data") or {}
            cmp_res = compare(extracted, truth)

            ok = bool(cmp_res["ok"])
            oks.append(ok)
            per_mode[mode].append(ok)

            rs = body.get("risk_score")
            if isinstance(rs, int):
                risk_scores.append(rs)

            sc = body.get("safe_cost_price")
            if isinstance(sc, (int, float)):
                safe_costs.append(float(sc))

            if not ok:
                failures.append({
                    "i": i,
                    "mode": mode,
                    "compare": cmp_res["checks"],
                    "truth": {k: truth[k] for k in ["nmck","execution_days","payment_terms_days","payment_after_full_delivery","delivery_by_customer_requests","supplier_must_hold_stock","has_vague_acceptance_terms"]},
                    "extracted": {k: extracted.get(k) for k in ["nmck","execution_days","payment_terms_days","payment_after_full_delivery","delivery_by_customer_requests","supplier_must_hold_stock","has_vague_acceptance_terms"]},
                })

        except Exception as e:
            failures.append({"i": i, "mode": mode, "error": repr(e)})
            oks.append(False)
            per_mode[mode].append(False)

        time.sleep(0.05)

    total = len(oks)
    passed = sum(1 for x in oks if x)
    acc = (passed / total) * 100 if total else 0.0

    print("\n=== SUMMARY ===")
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Accuracy: {acc:.1f}%")

    for m in ["safe", "trap", "hidden_loss"]:
        arr = per_mode[m]
        if arr:
            print(f"{m}: {sum(arr)}/{len(arr)} ({(sum(arr)/len(arr))*100:.1f}%)")

    if risk_scores:
        print("\nRisk score stats:")
        print(f"  mean: {statistics.mean(risk_scores):.2f}")
        print(f"  min:  {min(risk_scores)}")
        print(f"  max:  {max(risk_scores)}")

    if safe_costs:
        print("\nSafe cost stats:")
        print(f"  mean: {statistics.mean(safe_costs):.2f}")
        print(f"  min:  {min(safe_costs):.2f}")
        print(f"  max:  {max(safe_costs):.2f}")

    if failures:
        print("\n=== FAILURES (first 5) ===")
        for f in failures[:5]:
            print(json.dumps(f, ensure_ascii=False, indent=2))

        # сохраним полный отчёт
        out = "tools/test_report.json"
        with open(out, "w", encoding="utf-8") as fp:
            json.dump(failures, fp, ensure_ascii=False, indent=2)
        print(f"\nFull failure report saved: {out}")

if __name__ == "__main__":
    main()