#!/usr/bin/env python3
"""Фаза 2: оптимальное назначение лидеров 26 задач фазы 3.

Requires: Python >=3.10, scipy >=1.9. Data: input_model.json.
No external calls, does not write to GitHub. Run:
  python solve_allocation.py --input input_model.json --output-dir .
This file never claims that model scores represent real survey responses.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix


def solve(data: dict, fairness_weight: float | None = None, capacity: float | None = None) -> dict:
    tasks=data['tasks']; n=len(tasks); P=3; nv=n*P+1
    efforts=np.array([np.median(x) for x in data['individual_lead_hours']],dtype=float)
    prefs=np.array(data['individual_preferences'],dtype=float)
    available=np.array(data['eligible'],dtype=int)
    assert prefs.shape==(n,P) and available.shape==(n,P)
    assert np.all(efforts>0) and np.all((prefs>=1)&(prefs<=9))
    d=float(sum(t['shared_hours_per_person'] for t in tasks)) # same shared hours per expert
    p=data['parameters']; cap=float(capacity if capacity is not None else p['hours_capacity_per_person'])
    minh=float(p['minimum_hours_per_person']); minc=int(p['min_tasks_per_person']); maxc=int(p['max_tasks_per_person'])
    lam=float(fairness_weight if fairness_weight is not None else p['fairness_weight_lambda'])
    c=np.concatenate(((efforts[:,None]*(9.0-prefs)/8.0).reshape(-1),[lam]))
    lower=np.zeros(nv); upper=np.ones(nv); upper[:-1]=available.reshape(-1); upper[-1]=np.inf
    constraints=[]; lbs=[]; ubs=[]
    # exactly one accountable task owner, even for collaborative tasks
    for i in range(n):
        row=np.zeros(nv); row[i*P:(i+1)*P]=1
        constraints.append(row);lbs.append(1.0);ubs.append(1.0)
    for j in range(P):
        row=np.zeros(nv);row[j:-1:P]=efforts
        # min and max are total per person including unavoidable group participation
        constraints.append(row.copy());lbs.append(minh-d);ubs.append(cap-d)
        # makespan (max load) z >= d + sum(effort*x)
        row[-1]=-1
        constraints.append(row);lbs.append(-np.inf);ubs.append(-d)
        cnt=np.zeros(nv);cnt[j:-1:P]=1
        constraints.append(cnt);lbs.append(minc);ubs.append(maxc)
    A=np.stack(constraints)
    res=milp(c=c,integrality=np.concatenate((np.ones(n*P),[0])),bounds=Bounds(lower,upper),
             constraints=LinearConstraint(A,np.array(lbs),np.array(ubs)),
             options={'time_limit':60,'mip_rel_gap':0.0,'disp':False})
    if res.x is None or res.status!=0:
        raise RuntimeError(f'MILP did not return proven optimal solution: {res.message} (status {res.status})')
    x=np.rint(res.x[:-1]).reshape(n,P).astype(int)
    assert np.all(x.sum(axis=1)==1)
    assert np.all(x<=available)
    load=(x.T@efforts)+d
    task_count=x.sum(axis=0)
    assert np.all(load<=cap+1e-7) and np.all(load>=minh-1e-7)
    assert np.all(task_count>=minc) and np.all(task_count<=maxc)
    badness=float(np.sum(x*efforts[:,None]*(9-prefs)/8))
    avg_pref=float(np.sum(x*efforts[:,None]*prefs)/np.sum(efforts))
    z=float(load.max()); objective=float(badness+lam*z)
    assignments=[]
    for i,t in enumerate(tasks):
        j=int(np.argmax(x[i]))
        assignments.append({'task_id':t['id'],'stage':t['stage'],'task':t['name'],'owner':f'У{j+1}',
               'lead_hours':float(efforts[i]),'preference':int(prefs[i,j]),
               'shared_hours_each':float(t['shared_hours_per_person']),
               'cost':float(efforts[i]*(9-prefs[i,j])/8),
               'dependencies':t['dependencies'],'deliverable':t['deliverable']})
    sol={'status':'OPTIMAL','solver':'SciPy scipy.optimize.milp / HiGHS','solver_status':int(res.status),
         'mip_gap':float(res.mip_gap) if res.mip_gap is not None else None,
         'objective':objective,'dissatisfaction_hour_equivalents':badness,'fairness_weight_lambda':lam,
         'max_load_hours':z,'capacity_hours_per_person':cap,'min_hours_per_person':minh,
         'shared_hours_each_expert':d,'lead_hours_sum':float(efforts.sum()),
         'all_person_hours':float(efforts.sum()+P*d),
         'person_load_hours':{f'У{j+1}':round(float(load[j]),4) for j in range(P)},
         'lead_hours':{f'У{j+1}':round(float(load[j]-d),4) for j in range(P)},
         'task_count':{f'У{j+1}':int(task_count[j]) for j in range(P)},
         'weighted_mean_owner_preference':avg_pref,
         'assignments':assignments}
    return sol


def dump_solution(sol, output):
    output.mkdir(parents=True,exist_ok=True)
    (output/'allocation_solution.json').write_text(json.dumps(sol,ensure_ascii=False,indent=2),encoding='utf-8')
    with open(output/'allocation_solution.csv','w',newline='',encoding='utf-8-sig') as f:
        wr=csv.DictWriter(f,fieldnames=list(sol['assignments'][0].keys()));wr.writeheader()
        for x in sol['assignments']:
            row=x.copy();row['dependencies']=','.join(row['dependencies']);wr.writerow(row)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',type=Path,default=Path(__file__).with_name('input_model.json'))
    ap.add_argument('--output-dir',type=Path,default=Path(__file__).parent)
    ap.add_argument('--fairness-weight',type=float,default=None)
    args=ap.parse_args()
    data=json.loads(args.input.read_text(encoding='utf-8'))
    baseline=solve(data,fairness_weight=args.fairness_weight)
    dump_solution(baseline,args.output_dir)
    # Alternative fairness preferences; ranking/preference assumptions unchanged
    tests=[]
    for lam in [0.0,0.5,1.5,3.0,5.0]:
        r=solve(data,fairness_weight=lam)
        tests.append({'lambda':lam,'objective':r['objective'],'dissatisfaction_h_eq':r['dissatisfaction_hour_equivalents'],
                      'max_load_h':r['max_load_hours'],'min_load_h':min(r['person_load_hours'].values()),
                      'weighted_mean_preference':r['weighted_mean_owner_preference'],
                      **{f'load_{name}':h for name,h in r['person_load_hours'].items()},
                      'changed_vs_baseline':sum(x['owner']!=y['owner'] for x,y in zip(r['assignments'],baseline['assignments']))})
    with open(args.output_dir/'sensitivity.csv','w',newline='',encoding='utf-8-sig') as f:
        wr=csv.DictWriter(f,fieldnames=tests[0].keys());wr.writeheader();wr.writerows(tests)
    print('STATUS',baseline['status'],'MIP_GAP',baseline['mip_gap'])
    print('TOTAL_PERSON_HOURS',baseline['all_person_hours'],'TOTAL_OWNER_HOURS',baseline['lead_hours_sum'])
    print('OBJECTIVE',round(baseline['objective'],4),'DISSATISFACTION',round(baseline['dissatisfaction_hour_equivalents'],4),'MAX_LOAD',baseline['max_load_hours'])
    print('LOAD',baseline['person_load_hours'],'TASK_COUNT',baseline['task_count'])
    print('WEIGHTED_MEAN_PREFERENCE',round(baseline['weighted_mean_owner_preference'],4))
    print('SENSITIVITY',json.dumps(tests,ensure_ascii=False))
    print('ASSIGNMENT',[(x['task_id'],x['owner']) for x in baseline['assignments']])


if __name__=='__main__':main()
