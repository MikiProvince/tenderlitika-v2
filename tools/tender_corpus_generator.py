import random
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple, List

TRAP_FLAGS = [
    "payment_after_full_delivery",
    "delivery_by_customer_requests",
    "supplier_must_hold_stock",
    "has_vague_acceptance_terms",
]

@dataclass
class TenderTruth:
    nmck: int
    execution_days: int
    payment_terms_days: int
    bid_security_percent: float
    contract_security_percent: float
    advance_percent: float
    penalty_percent_per_day: float
    payment_after_full_delivery: bool
    delivery_by_customer_requests: bool
    supplier_must_hold_stock: bool
    has_vague_acceptance_terms: bool

def _price() -> int:
    return random.randint(5, 80) * 1_000_000

def _pct(options: List[float]) -> float:
    return float(random.choice(options))

def generate_tender(mode: str = "trap") -> Tuple[str, Dict[str, Any]]:
    """
    mode: safe | trap | hidden_loss
    returns: (text, truth_dict)
    """
    nmck = _price()

    if mode == "safe":
        truth = TenderTruth(
            nmck=nmck,
            execution_days=random.randint(45, 120),
            payment_terms_days=random.randint(10, 30),
            bid_security_percent=_pct([0.0, 1.0, 2.0, 3.0]),
            contract_security_percent=_pct([5.0, 10.0]),
            advance_percent=_pct([10.0, 20.0, 30.0]),
            penalty_percent_per_day=_pct([0.02, 0.03, 0.05, 0.1]),
            payment_after_full_delivery=False,
            delivery_by_customer_requests=False,
            supplier_must_hold_stock=False,
            has_vague_acceptance_terms=False,
        )

        text = f"""
Предмет закупки: поставка офисной мебели.

Начальная максимальная цена контракта: {truth.nmck} рублей.

Срок исполнения контракта — не позднее {truth.execution_days} календарных дней с даты заключения контракта.

Оплата производится в течение {truth.payment_terms_days} календарных дней после подписания акта приемки.

Авансовый платеж предусмотрен: {int(truth.advance_percent)}%.

Обеспечение исполнения контракта — {int(truth.contract_security_percent)}% от цены контракта.
Обеспечение заявки — {int(truth.bid_security_percent)}% от цены контракта.

За каждый день просрочки начисляется пеня {truth.penalty_percent_per_day}%/день.
""".strip()

        return text, asdict(truth)

    # TRAP / HIDDEN LOSS
    # базовые числа одинаковые
    truth = TenderTruth(
        nmck=nmck,
        execution_days=random.randint(30, 90),
        payment_terms_days=random.randint(20, 60),
        bid_security_percent=_pct([0.0, 2.0, 5.0]),
        contract_security_percent=_pct([10.0, 15.0, 20.0, 25.0]),
        advance_percent=_pct([0.0, 0.0, 10.0]),  # чаще 0
        penalty_percent_per_day=_pct([0.1, 0.2, 0.3, 0.4]),
        payment_after_full_delivery=True,                 # ключевая ловушка
        delivery_by_customer_requests=True,               # ключевая ловушка
        supplier_must_hold_stock=True,                    # ключевая ловушка
        has_vague_acceptance_terms=True if random.random() < 0.6 else False,
    )

    # для hidden_loss сделаем ещё хуже
    if mode == "hidden_loss":
        truth.payment_terms_days = 60
        truth.advance_percent = 0.0
        truth.contract_security_percent = 25.0
        truth.penalty_percent_per_day = 0.4

    vague_block = ""
    if truth.has_vague_acceptance_terms:
        vague_block = """
Заказчик вправе по результатам приемки требовать устранения выявленных недостатков до подписания акта.
Решение о приемке принимается по усмотрению заказчика.
""".strip()

    text = f"""
Предмет закупки: поставка и ввод в эксплуатацию оборудования.

Начальная максимальная цена контракта: {truth.nmck} рублей.

Срок исполнения контракта — не позднее {truth.execution_days} календарных дней с даты заключения контракта.

Поставка осуществляется партиями по заявкам заказчика.
Заказчик вправе направлять заявки на поставку отдельных партий товара в течение всего срока исполнения контракта.
Поставщик обязан обеспечить наличие необходимого количества товара для исполнения заявок заказчика.

Оплата производится в течение {truth.payment_terms_days} календарных дней после подписания итогового акта исполнения обязательств по контракту.
Подписание итогового акта производится после поставки всего объема товара и выполнения всех работ.

{vague_block}

Авансовый платеж: {int(truth.advance_percent)}%.

Обеспечение исполнения контракта — {int(truth.contract_security_percent)}% от цены контракта.
Обеспечение заявки — {int(truth.bid_security_percent)}% от цены контракта.

За каждый день просрочки начисляется штраф {truth.penalty_percent_per_day}%/день.
""".strip()

    return text, asdict(truth)


if __name__ == "__main__":
    for m in ["safe", "trap", "hidden_loss"]:
        txt, truth = generate_tender(m)
        print(f"\n=== {m.upper()} ===\n")
        print(txt)
        print("\nTRUTH:", truth)