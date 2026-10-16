# Independent re-derivation (review) of the Banko / Oranli test numbers straight from
# baseline_predictions_full.csv.gz, re-implementing headline_picks.select_headline_picks (fair path only).
import csv, gzip, math
from collections import defaultdict
P = r"C:/Users/Mito/Downloads/FootballIntelligence-main/FootballIntelligence-main/backend/data/training/baseline_predictions_full.csv.gz"
KEYS = ["HOME_WIN","DRAW","AWAY_WIN","HOME_OR_DRAW","HOME_OR_AWAY","DRAW_OR_AWAY","UNDER_1_5","OVER_1_5","UNDER_2_5","OVER_2_5","UNDER_3_5","OVER_3_5","BTTS_NO","BTTS_YES"]
FAM = [0]*6 + [1]*8
def f(x):
    try: return float(x)
    except: return float('nan')
rows=[]
with gzip.open(P,'rt',encoding='utf-8') as fh:
    for r in csv.DictReader(fh):
        if r['status']!='ok': continue
        rows.append(r)
def probs(r):
    ph,pd,pa=f(r['p_home']),f(r['p_draw']),f(r['p_away'])
    o15,o25,o35,bt=f(r['p_over15']),f(r['p_over25']),f(r['p_over35']),f(r['p_btts'])
    return [ph,pd,pa,ph+pd,ph+pa,pd+pa,1-o15,o15,1-o25,o25,1-o35,o35,1-bt,bt]
def outc(h,a):
    t=h+a
    return [h>a,h==a,h<a,h>=a,h!=a,h<=a,t<1.5,t>1.5,t<2.5,t>2.5,t<3.5,t>3.5,h==0 or a==0,h>0 and a>0]
def select(p, lo=0.70, hi=0.95):
    order = sorted(range(14), key=lambda i: -p[i])  # stable: ties keep rail order
    b = next((i for i in order if lo <= p[i] <= hi), None)
    fam = FAM[b] if b is not None else None
    fair = [i for i in order if FAM[i]!=fam and 1/p[i] >= 1.6 and p[i] >= 0.45]
    o = fair[0] if fair else None
    return b, o
def wilson(k,n,z=1.6448536):
    ph=k/n; d=1+z*z/n; c=(ph+z*z/(2*n))/d; h=z*math.sqrt(ph*(1-ph)/n+z*z/(4*n*n))/d; return round(c-h,4),round(c+h,4)
test=[r for r in rows if r['split']=='test']
days=len(set(r['kickoff'][:10] for r in test))
print('test rows',len(test),'days',days, 'euro', sum(r['comp_type']!='league' for r in test))
for name,lo,minp_or in [('R0',0.70,None),('R1',0.85,None),('R3',0.90,None)]:
    k=n=0
    for r in test:
        p=probs(r); y=outc(int(r['home_goals']),int(r['away_goals']))
        b,_=select(p,0.70)  # app rule picks most likely in [0.70,0.95]; R1 = shown only if p>=lo
        if b is None or p[b] < lo: continue
        n+=1; k+=y[b]
    print(name,'n',n,'hit',round(k/n,4),wilson(k,n),'per_day',round(n/days,2),'cov',round(n/len(test),4))
for lo_or in [None,0.55,0.58]:
    k=n=0
    for r in test:
        p=probs(r); y=outc(int(r['home_goals']),int(r['away_goals']))
        b,o=select(p,0.70)
        if o is None: continue
        if lo_or and p[o] < lo_or: continue
        n+=1; k+=y[o]
    print('oranli fair, min p',lo_or,'n',n,'hit',round(k/n,4),'cov',round(n/len(test),4))
# Oranli when banko rule is R1 (banko only if p>=0.85): family exclusion changes
for lo_or in [None,0.55]:
    k=n=0
    for r in test:
        p=probs(r); y=outc(int(r['home_goals']),int(r['away_goals']))
        b,o=select(p,0.85)
        if o is None: continue
        if lo_or and p[o] < lo_or: continue
        n+=1; k+=y[o]
    print('oranli fair with R1 banko, min p',lo_or,'n',n,'hit',round(k/n,4),'cov',round(n/len(test),4))
