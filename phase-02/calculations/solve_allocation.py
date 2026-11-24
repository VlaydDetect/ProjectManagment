"""Reproducible assignment of Phase 3 educational assessment tasks (not app development).
Run: python phase-02/calculations/solve_allocation.py --input phase-02/input/model_task_data.json
Requires scipy>=1.11 no proprietary optimizer. MILP (HiGHS via scipy.optimize.milp).
Scores & availability are demonstrative replace with participant-approved inputs before submission.
"""
import argparse, csv, json, statistics, math
from pathlib import Path
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'phase-02/input/model_task_data.json'
OUTPUT = ROOT / 'phase-02/calculations'
# Ineligible roles in the teaching exercise are tentative and may be revised by the group.
ELIGIBILITY = {
    'COSMIC': {2, 3}, 'UCP': {2, 3}, 'Экспертиза': {1, 2, 3},
    'UC': {1, 2, 3}, 'Анализ': {1, 2, 3}, 'Отчёт': {1, 3}, 'Управление': {1},
    'Согласование': {1, 2, 3}, 'Постановка': {1, 2, 3}
}
# More specific capability safeguard: specialist should own primary technical checks.
MANDATORY = {
    'T33': {2, 3}, 'T34': {2, 3}, 'T35': {2, 3}, 'T36': {2, 3}, 'T37': {2, 3},
    'T38': {2, 3}, 'T39': {2, 3}, 'T40': {2, 3}, 'T41': {2, 3}, 'T42': {2, 3},
    'T53': {1}
}


def solve(data, fairness=3.0, cap=32.0):
    tasks = data['tasks']
    singles = [r for r in tasks if r['kind'] == 'Индивидуальное']
    shared = [r for r in tasks if r['kind'] == 'Общее']
    n = len(singles)
    nv = n * 3 + 2
    maxidx = n * 3
    minidx = n * 3 + 1
    c = np.zeros(nv, float)
    lo = np.zeros(nv)
    hi = np.ones(nv)
    integrality = np.zeros(nv, int)
    base = np.array([sum(t['estimates'][p] for t in shared) for p in range(3)], float)
    lo[maxidx] = 0
    lo[minidx] = 0
    hi[maxidx] = 1e6
    hi[minidx] = 1e6
    for i, t in enumerate(singles):
        effort = float(statistics.median(t['estimates']))
        for p in range(3):
            k = i * 3 + p
            c[k] = effort * (5 - float(t['preferences'][p]))
            integrality[k] = 1
            if (p + 1) not in (
            set(MANDATORY[t['id']]) & set(data.get('eligibility_by_group', {}).get(t['group'], {1, 2, 3})) if t[
                                                                                                                  'id'] in MANDATORY else set(
                    data.get('eligibility_by_group', {}).get(t['group'], ELIGIBILITY.get(t['group'], {1, 2, 3})))):
                hi[k] = 0
    c[maxidx] = fairness
    c[minidx] = -fairness
    rows = []
    low = []
    up = []
    for i in range(n):
        row = np.zeros(nv)
        row[i * 3:i * 3 + 3] = 1
        rows.append(row)
        low.append(1)
        up.append(1)
    for p in range(3):
        row = np.zeros(nv)
        for i, t in enumerate(singles): row[i * 3 + p] = float(statistics.median(t['estimates']))
        rows.append(row)
        low.append(-np.inf)
        up.append(cap - base[p])
        rowmax = row.copy()
        rowmax[maxidx] = -1
        rows.append(rowmax)
        low.append(-np.inf)
        up.append(-base[p])
        rowmin = row.copy()
        rowmin[minidx] = -1
        rows.append(rowmin)
        low.append(-base[p])
        up.append(np.inf)
    res = milp(c=c, integrality=integrality, bounds=Bounds(lo, hi),
               constraints=LinearConstraint(np.array(rows), np.array(low), np.array(up)),
               options={'mip_rel_gap': 0.0, 'time_limit': 60})
    if res.x is None or res.status != 0: raise RuntimeError(
        f'No proved optimum: status={res.status}, message={res.message}')
    x = res.x
    assignments = {}
    workload = base.copy()
    disutil = 0
    for i, t in enumerate(singles):
        p = int(np.argmax(x[3 * i:3 * i + 3]))
        assert x[3 * i + p] > 0.999
        assignments[t['id']] = p + 1
        h = float(statistics.median(t['estimates']))
        workload[p] += h
        disutil += h * (5 - t['preferences'][p])
    assert np.all(workload <= cap + 1e-6)
    assert abs(workload.sum() - (sum(float(statistics.median(t['estimates'])) for t in singles) + base.sum())) < 1e-8
    assert abs(res.fun - (disutil + fairness * (max(workload) - min(workload)))) < 1e-5
    return {'status': int(res.status), 'message': str(res.message), 'mip_gap': float(res.mip_gap),
            'objective': float(res.fun), 'disutility': disutil, 'load_spread': float(max(workload) - min(workload)),
            'fairness_lambda': fairness, 'cap_person_hours': cap, 'total_person_hours': float(workload.sum()),
            'shared_hours_by_person': base.tolist(),
            'workload_by_person': workload.tolist(), 'assignment': assignments, 'assignable_tasks': len(singles),
            'joint_tasks': len(shared)}


def main():
    ar = argparse.ArgumentParser()
    ar.add_argument('--input', type=Path, default=INPUT)
    ar.add_argument('--out-dir', type=Path, default=OUTPUT)
    ar.add_argument('--fairness', type=float, default=3.0)
    ar.add_argument('--capacity', type=float, default=32.0)
    args = ar.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    args.out_dir.mkdir(exist_ok=True, parents=True)
    ss = [solve(data, fairness=q, cap=args.capacity) for q in (0, 1, 3, 6, 12)]
    primary = solve(data, fairness=args.fairness, cap=args.capacity)
    (args.out_dir / 'allocation_solution.json').write_text(json.dumps(
        {'note': 'DEMONSTRATION: synthetic effort/preferences/competence, not participant-verified', **primary},
        ensure_ascii=False, indent=2), encoding='utf-8')
    with (args.out_dir / 'allocation_solution.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter='')
        writer.writerow(
            ['ID', 'Работа', 'Тип', 'Область', 'Инд. оценка 1', 'Инд. оценка 2', 'Инд. оценка 3', 'Медиана (ч)',
             'Предпочт. 1', 'Предпочт. 2', 'Предпочт. 3', 'Назначен', 'У1, ч', 'У2, ч', 'У3, ч', 'Выходной артефакт'])
        for t in data['tasks']:
            if t['kind'] == 'Общее':
                owner = 'Все трое'
                hs = t['estimates']
                m = '—'
            else:
                p = primary['assignment'][t['id']]
                owner = f'У{p}'
                m = float(statistics.median(t['estimates']))
                hs = [m if i == p - 1 else 0 for i in range(3)]
            writer.writerow(
                [t['id'], t['title'], t['kind'], t['group'], *t['estimates'], m, *t['preferences'], owner, *hs,
                 t['deliverable']])
    with (args.out_dir / 'sensitivity.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter='')
        writer.writerow(
            ['lambda', 'Целевая функция', 'Штраф предпочтений', 'Разница макс-мин, ч', 'У1, ч', 'У2, ч', 'У3, ч',
             'Задачи 1', 'Задачи 2', 'Задачи 3', 'MIP-gap'])
        for s in ss:
            ass = s['assignment']
            writer.writerow(
                [s['fairness_lambda'], s['objective'], s['disutility'], s['load_spread'], *s['workload_by_person'],
                 *[sum(v == p for v in ass.values()) for p in (1, 2, 3)], s['mip_gap']])
    print('PRIMARY', json.dumps(primary, ensure_ascii=False, indent=2))
    print('SENSITIVITY',
          [{k: z[k] for k in ['fairness_lambda', 'disutility', 'load_spread', 'workload_by_person']} for z in ss])


if __name__ == '__main__': main()
