"""Frozen 15-candidate research screen. No broker, secrets, orders or Jev calls.

Input: one-minute UTC bar-open OHLCV CSV. Published prices are ASSUMED mids;
the public sample does not establish quote-side provenance. See REPORT.md.
Signals use closed bars; entries use the next one-minute open; stop first on
ambiguous bars. All values are per-price-unit, not futures contract dollars.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
CONFIG=json.loads((ROOT/'strategies.json').read_text())
NY='America/New_York'

def wilder(s,n=14):
    """SMA seeded Wilder average, unlike an unseeded pandas EWM."""
    a=s.to_numpy(dtype=float);out=np.full(len(a),np.nan)
    if len(a)>=n:
        seed=next((i for i in range(n-1,len(a)) if np.isfinite(a[i-n+1:i+1]).all()),None)
        if seed is not None:
            out[seed]=a[seed-n+1:seed+1].mean()
            for i in range(seed+1,len(a)):out[i]=(out[i-1]*(n-1)+a[i])/n
    return pd.Series(out,index=s.index)

def load_data(path):
    d=pd.read_csv(path)
    required={'datetime','open','high','low','close','volume'}
    if not required.issubset(d):raise ValueError('Required columns: '+str(sorted(required)))
    d.index=pd.to_datetime(d.pop('datetime'),utc=True)
    if not d.index.is_monotonic_increasing or d.index.has_duplicates:raise ValueError('Unsorted/duplicate timestamps')
    if not np.isfinite(d.to_numpy()).all():raise ValueError('Nonfinite OHLCV')
    if (d[['open','high','low','close']]<=0).any().any():raise ValueError('Nonpositive price')
    if (d.high<d[['open','close','low']].max(axis=1)).any() or (d.low>d[['open','close','high']].min(axis=1)).any():raise ValueError('Invalid OHLC')
    if (d.volume<0).any():raise ValueError('Negative volume')
    return d

def features(raw,tf):
    rule=f'{tf}min'
    d=raw.resample(rule,label='right',closed='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
    n=raw.close.resample(rule,label='right',closed='left').count()
    d=d.loc[n==tf].copy() # never manufacture incomplete bars
    for length in [9,20,21,50,200]:
        # Recursive EMA seeded at first observed close; 500 H1-bar warmup below.
        d[f'e{length}']=d.close.ewm(span=length,adjust=False,min_periods=length).mean()
    prev=d.close.shift(1)
    tr=pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1)
    d['atr']=wilder(tr)
    delta=d.close.diff();up=wilder(delta.clip(lower=0));down=wilder(-delta.clip(upper=0))
    d['rsi']=100-100/(1+up/down.replace(0,np.nan))
    d.loc[(down==0)&(up>0),'rsi']=100;d.loc[(up==0)&(down==0),'rsi']=50
    up2=wilder(delta.clip(lower=0),2);down2=wilder(-delta.clip(upper=0),2)
    d['rsi2']=100-100/(1+up2/down2.replace(0,np.nan))
    d.loc[(down2==0)&(up2>0),'rsi2']=100;d.loc[(up2==0)&(down2==0),'rsi2']=50
    local=d.index.tz_convert(NY);d['day']=local.date;d['minute']=local.hour*60+local.minute
    d['weekday']=local.weekday
    # Prior 20 observations at the same local time; >=10 distinct earlier dates.
    med=d.groupby('minute',sort=False).volume.transform(lambda x:x.shift(1).rolling(20,min_periods=10).median())
    d['rvol']=d.volume/med.replace(0,np.nan)
    d['er']=d.close.diff(10).abs()/d.close.diff().abs().rolling(10).sum().replace(0,np.nan)
    ph=np.full(len(d),np.nan);pl=ph.copy();last_h=last_l=np.nan
    h=d.high.to_numpy();l=d.low.to_numpy()
    for j in range(4,len(d)):
        k=j-2
        if h[k]>max(h[k-2],h[k-1],h[k+1],h[k+2]):last_h=h[k]
        if l[k]<min(l[k-2],l[k-1],l[k+1],l[k+2]):last_l=l[k]
        ph[j]=last_h;pl[j]=last_l
    d['pivot_h']=ph;d['pivot_l']=pl
    return d

def attach_h1(d,h1):
    h=h1[['e20','e50','e200','close','atr']].copy()
    h['slope']=h1.e20-h1.e20.shift(3);h['n']=np.arange(len(h))+1
    h['available_at']=h.index
    h=h.reindex(d.index,method='ffill').add_prefix('h1_')
    d=d.join(h)
    age=(d.index-d.h1_available_at).dt.total_seconds()
    d['h1_ok']=(age>=0)&(age<=3600)&(d.h1_n>=CONFIG['min_h1_bars'])
    return d

def time_ok(minute,windows):return any(a<=minute<b for a,b in windows)

def blackout(minute):
    # Fixed precautionary proxy, NOT a historical economic-event calendar.
    return any(a<=minute<b for a,b in [(505,525),(595,605),(835,855)])

def side_h1(r):
    if r.h1_e20>r.h1_e50 and r.h1_slope>0:return 1
    if r.h1_e20<r.h1_e50 and r.h1_slope<0:return -1
    return 0

def generate_candidates(raw,spec,cache=None,revision='strict'):
    tf=spec['tf'];family=spec['family']
    simple=revision=='simple'
    if cache is None:cache={}
    for x in [tf,60]:
        if x not in cache:cache[x]=features(raw,x)
    d=attach_h1(cache[tf].copy(),cache[60]);d['vwap']=np.nan;d['vstd']=np.nan
    if family=='vwap_revert':
        active=(d.minute>=spec['anchor']+tf)&(d.minute<=950)
        z=d.loc[active];typ=(z.high+z.low+z.close)/3
        w=z.volume.groupby(z.day).cumsum()
        mean=(typ*z.volume).groupby(z.day).cumsum()/w.replace(0,np.nan)
        var=(typ.pow(2)*z.volume).groupby(z.day).cumsum()/w.replace(0,np.nan)-mean.pow(2)
        d.loc[active,'vwap']=mean;d.loc[active,'vstd']=np.sqrt(var.clip(lower=0))
    levels={}
    if family=='sweep_fvg':
        local=raw.index.tz_convert(NY);mins=local.hour*60+local.minute
        z=raw.loc[(mins>=240)&(mins<spec['level_end'])].copy();z['day']=z.index.tz_convert(NY).date
        # Frozen range is available only after level_end; each signal window starts later.
        for day,g in z.groupby('day'):
            if len(g)>=.95*(spec['level_end']-240):levels[day]=(g.high.max(),g.low.min())
    records=[];rows=list(d.itertuples());sweep=None;gap=None;impulse=None;lastday=None
    def emit(j,side,stop,reason,volume_ok,target=None):
        r=rows[j]
        if not np.isfinite(stop) or side*(r.close-stop)<=0:return
        records.append({'signal_time':r.Index,'side':side,'stop':float(stop),'atr':float(r.atr),
                        'rvol':float(r.rvol),'volume_ok':bool(volume_ok),'target_price':target,
                        'reason':reason,'row':j})
    for j in range(205,len(rows)):
        r=rows[j];p=rows[j-1]
        if lastday!=r.day:sweep=gap=impulse=None;lastday=r.day
        contiguous=(r.Index-p.Index)==pd.Timedelta(minutes=tf)
        if not contiguous:sweep=gap=impulse=None
        if not (r.h1_ok and np.isfinite(r.atr) and r.atr>0 and r.weekday<5):continue
        eligible=time_ok(r.minute,spec['windows']) and not blackout(r.minute)
        trend=side_h1(r);a=r.atr;side=0
        if family=='sweep_fvg':
            if not eligible or r.day not in levels:sweep=gap=None;continue
            high,low=levels[r.day]
            # Retest is strictly later than gap formation. Undercutting the sweep invalidates.
            if gap is not None:
                g=gap;s=g['side']
                invalid=(s==1 and r.low<=g['extreme']) or (s==-1 and r.high>=g['extreme'])
                if j-g['j']>3 or invalid:gap=None
                elif ((s==1 and r.low<=g['hi'] and r.close>g['mid'] and r.close>r.open)
                      or (s==-1 and r.high>=g['lo'] and r.close<g['mid'] and r.close<r.open)):
                    emit(j,s,g['extreme']-s*.1*a,'sweep>MSS>FVG>closed retest',g['volume_ok'])
                    gap=None;sweep=None;continue
            if sweep is not None and gap is None:
                q=sweep;s=q['side'];k=rows[j-2]
                if j-q['j']>4 or (s==1 and r.low<q['extreme']) or (s==-1 and r.high>q['extreme']):sweep=None
                elif simple and j>q['j'] and s*(r.close-q['break'])>0:
                    emit(j,s,q['extreme']-s*.1*a,'sweep>closed micro-MSS (no FVG filter)',r.rvol>=1.2)
                    sweep=None;continue
                elif j>q['j'] and s*(p.close-p.open)>=.8*rows[j-2].atr and s*(r.close-q['break'])>0:
                    lo,hi=(k.high,r.low) if s==1 else (r.high,k.low)
                    if hi-lo>=.1*a:
                        gap={'j':j,'side':s,'lo':lo,'hi':hi,'mid':(lo+hi)/2,'extreme':q['extreme'],
                             'volume_ok':np.isfinite(p.rvol) and p.rvol>=1.2}
            if sweep is None and gap is None:
                bull=r.low<low-.05*a and r.close>low and (simple or trend==1) and np.isfinite(p.pivot_h)
                bear=r.high>high+.05*a and r.close<high and (simple or trend==-1) and np.isfinite(p.pivot_l)
                bh=max(x.high for x in rows[j-3:j]) if simple else p.pivot_h
                bl=min(x.low for x in rows[j-3:j]) if simple else p.pivot_l
                if bull and not bear:sweep={'j':j,'side':1,'extreme':r.low,'break':bh}
                elif bear and not bull:sweep={'j':j,'side':-1,'extreme':r.high,'break':bl}
        elif family=='ema_rsi' and eligible and contiguous:
            bull_reset=(50<r.rsi<=65) if simple else (p.rsi<=50<r.rsi<=65)
            bear_reset=(35<=r.rsi<50) if simple else (35<=r.rsi<50<=p.rsi)
            if r.e9>r.e21>r.e50 and r.e21>rows[j-3].e21 and p.low<=p.e21 and p.close>=p.e50 and bull_reset and r.close>p.high and trend==1:side=1
            if r.e9<r.e21<r.e50 and r.e21<rows[j-3].e21 and p.high>=p.e21 and p.close<=p.e50 and bear_reset and r.close<p.low and trend==-1:side=-1
            if side:
                stop=min(x.low for x in rows[j-2:j+1])-.1*a if side==1 else max(x.high for x in rows[j-2:j+1])+.1*a
                emit(j,side,stop,'9/21/50 EMA + RSI50 pullback recovery',r.rvol>=1)
        elif family=='vwap_revert' and eligible and contiguous:
            quiet=(r.er<=.35) if simple else (abs(r.e20-r.e50)<=.35*a and abs(r.e50-rows[j-3].e50)<=.15*a)
            if quiet and np.isfinite(p.vwap) and np.isfinite(r.vwap):
                bull=(p.rsi2<=10<r.rsi2 and r.close>p.close) if simple else (p.rsi<=30<r.rsi and r.close>p.high)
                bear=(p.rsi2>=90>r.rsi2 and r.close<p.close) if simple else (p.rsi>=70>r.rsi and r.close<p.low)
                if p.close<p.vwap-1.5*p.vstd and bull:side=1
                if p.close>p.vwap+1.5*p.vstd and bear:side=-1
                if side:
                    stop=min(x.low for x in rows[j-2:j+1])-.1*a if side==1 else max(x.high for x in rows[j-2:j+1])+.1*a
                    emit(j,side,stop,'range-only tick-weighted VWAP + RSI reclaim',np.isfinite(r.rvol) and r.rvol<=1.2,float(r.vwap))
        elif family=='dtfx_pullback':
            if not eligible:impulse=None;continue
            if impulse is not None:
                q=impulse;s=q['side'];length=q['hi']-q['lo']
                invalid=(s==1 and r.low<=q['lo']) or (s==-1 and r.high>=q['hi'])
                if j-q['j']>8 or invalid or trend!=s:impulse=None
                elif j>q['j']:
                    if s==1:
                        zlo=q['hi']-.7*length;zhi=q['hi']-.5*length
                        touch=r.low<=zhi and r.high>=zlo
                        q['touched']=q.get('touched',False) or touch
                        trigger=(q['touched'] if simple else touch) and r.close>zhi and r.close>(p.close if simple else p.high) and r.close>r.open
                    else:
                        zlo=q['lo']+.5*length;zhi=q['lo']+.7*length
                        touch=r.high>=zlo and r.low<=zhi
                        q['touched']=q.get('touched',False) or touch
                        trigger=(q['touched'] if simple else touch) and r.close<zlo and r.close<(p.close if simple else p.low) and r.close<r.open
                    if trigger:
                        stop=q['lo']-.1*a if s==1 else q['hi']+.1*a
                        emit(j,s,stop,'confirmed BOS > frozen impulse > 50-70% recovery',q['volume_ok']);impulse=None;continue
            if impulse is None and contiguous:
                if trend==1 and np.isfinite(p.pivot_h) and p.close<=p.pivot_h<r.close and np.isfinite(p.pivot_l):
                    lo,hi=p.pivot_l,(p.pivot_h if simple else r.high);side=1
                elif trend==-1 and np.isfinite(p.pivot_l) and p.close>=p.pivot_l>r.close and np.isfinite(p.pivot_h):
                    lo,hi=(p.pivot_l if simple else r.low),p.pivot_h;side=-1
                if side and hi-lo>=(1.0 if simple else 1.5)*a and (simple or side*(r.close-r.open)>=.6*a):
                    impulse={'j':j,'side':side,'lo':lo,'hi':hi,'volume_ok':r.rvol>=1.2}
        elif family=='ema_trend' and eligible and contiguous:
            bull=(r.close>r.e20 and r.close>p.close) if simple else (r.close>p.high and r.er>=.25)
            bear=(r.close<r.e20 and r.close<p.close) if simple else (r.close<p.low and r.er>=.25)
            if r.e20>r.e50>r.e200 and r.e20>rows[j-3].e20 and p.low<=p.e20 and p.close>=p.e50 and bull and 50<=r.rsi<=70 and trend==1:side=1
            if r.e20<r.e50<r.e200 and r.e20<rows[j-3].e20 and p.high>=p.e20 and p.close<=p.e50 and bear and 30<=r.rsi<=50 and trend==-1:side=-1
            if side:emit(j,side,r.close-side*1.5*a,'20/50/200 EMA + RSI band + efficiency pullback',r.rvol>=1)
    return records,d

def bar_exit(side,entry,stop,target,o,h,l,halfspread,slip):
    """Exit-side OHLC. Opening gaps are ordered before intrabar ambiguity."""
    qo=o-side*halfspread;qh=h-side*halfspread;ql=l-side*halfspread
    if side*(qo-stop)<=0:return qo-side*slip,'gap_stop'
    if target is not None and side*(qo-target)>=0:return target,'gap_target_conservative'
    hitstop=(ql<=stop) if side==1 else (qh>=stop)
    hittarget=target is not None and ((qh>=target) if side==1 else (ql<=target))
    if hitstop:return stop-side*slip,'both_stop_first' if hittarget else 'stop'
    if hittarget:return target,'target'
    return None,None

def simulate(raw,candidates,d,spec,cost_mult=1.,volume=True,delay=0):
    sym=spec['symbol'];spread=CONFIG['spreads'][sym]*cost_mult;hs=spread/2;slip=CONFIG['slippage_each_side'][sym]*cost_mult
    idx=raw.index;v=raw[['open','high','low','close']].to_numpy();minute=idx.tz_convert(NY).hour*60+idx.tz_convert(NY).minute
    lookup={t:i for i,t in enumerate(idx)};barlookup={t:i for i,t in enumerate(d.index)}
    trades=[];counts=defaultdict(int);busy=-1;losses=defaultdict(float);rejected=defaultdict(int)
    for q in candidates:
        ts=q['signal_time']+pd.Timedelta(minutes=delay);day=ts.tz_convert(NY).date()
        if volume and not q['volume_ok']:rejected['volume']+=1;continue
        k=lookup.get(ts)
        if k is None:rejected['missing_entry_minute']+=1;continue
        if k<=busy or counts[day]>=spec['max_daily'] or losses[day]<=-2:rejected['capacity_or_day_stop']+=1;continue
        if not time_ok(minute[k],spec['windows']) or blackout(minute[k]):rejected['deadline_or_blackout']+=1;continue
        side=q['side'];stop=q['stop'];entry=v[k,0]+side*(hs+slip)
        R=side*(entry-stop)+slip
        if side*(v[k,0]-stop)<=0 or not (.6*q['atr']<=R<=3*q['atr']):rejected['stop_distance']+=1;continue
        if (spread+2*slip)/R>CONFIG['cost_gate_fraction']:rejected['cost_gate']+=1;continue
        if abs(v[k,0]-raw.loc[q['signal_time']-pd.Timedelta(minutes=1),'close'])>.25*q['atr']:
            rejected['entry_jump']+=1;continue
        target=q['target_price']
        if target is None and spec['target_r'] is not None:target=entry+side*spec['target_r']*R
        if q['target_price'] is not None and not 1.2<=side*(target-entry)/R<=3:rejected['target_room']+=1;continue
        deadline=min(ts+pd.Timedelta(minutes=spec['max_hold']),pd.Timestamp(str(day)+' 15:50',tz=NY).tz_convert('UTC'))
        exitprice=None;reason=None;trailstop=stop;lasttrail=k;exit_time=None
        for z in range(k,len(raw)):
            # Missing minutes: record uncertain liquidation rather than inventing a path.
            if z>k and idx[z]-idx[z-1]>pd.Timedelta(minutes=1):
                exitprice=v[z,0]-side*(hs+slip);reason='data_gap_exit_unresolved';exit_time=idx[z];break
            if idx[z]>=deadline:
                exitprice=v[z,0]-side*(hs+slip);reason='time';exit_time=idx[z];break
            if spec['family']=='ema_trend' and idx[z] in barlookup and z>k:
                b=d.iloc[barlookup[idx[z]]]
                proposal=b.close-side*2*b.atr
                trailstop=max(trailstop,proposal) if side==1 else min(trailstop,proposal)
                if side*(b.close-b.e20)<0:
                    exitprice=v[z,0]-side*(hs+slip);reason='ema20_exit';exit_time=idx[z];break
            exitprice,reason=bar_exit(side,entry,trailstop,target,*v[z,:3],hs,slip)
            if exitprice is not None:exit_time=idx[z]+pd.Timedelta(minutes=1);break
        if exitprice is None:
            z=len(raw)-1;exitprice=v[z,3]-side*(hs+slip);reason='data_end';exit_time=idx[z]+pd.Timedelta(minutes=1)
        net=side*(exitprice-entry)/R
        trades.append({'id':spec['id'],'symbol':sym,'family':spec['family'],'category':spec['category'],
                       'volume_filter':volume,'cost_mult':cost_mult,'delay_minutes':delay,'day':str(day),
                       'signal_time':q['signal_time'].isoformat(),'entry_time':ts.isoformat(),'exit_time':exit_time.isoformat(),
                       'side':side,'entry':entry,'stop_initial':stop,'exit':exitprice,'R_price':R,'net_R':net,'exit_reason':reason,
                       'rvol':q['rvol'],'roundtrip_cost_R':(spread+2*slip)/R,'hold_minutes':(exit_time-ts).total_seconds()/60})
        # Conservatively reserve the complete exit minute, including scheduled exits.
        busy=z;counts[day]+=1;losses[day]+=net
    return pd.DataFrame(trades),dict(rejected)

def metrics(trades,days,seed=4321):
    vals=trades.net_R.to_numpy() if len(trades) else np.array([])
    if not len(vals):return {'trades':0,'win_rate':None,'avg_R':None,'total_R':0.,'PF':None,'drawdown_R':0.,'ci_low':None,'ci_high':None,'day_mean_R':0.,'p_boot_one_sided':1.}
    gains=vals[vals>0].sum();loss=-vals[vals<0].sum();eq=np.r_[0,vals.cumsum()]
    grouped=trades.groupby('day').net_R.agg(['sum','count']).reindex(days,fill_value=0)
    daily=grouped['sum'].to_numpy();counts=grouped['count'].to_numpy();n=len(daily)
    rng=np.random.default_rng(seed);B=3000;block=5
    ix=(rng.integers(0,n,size=(B,math.ceil(n/block)))[:,:,None]+np.arange(block))%n
    ix=ix.reshape(B,-1)[:,:n];den=counts[ix].sum(axis=1)
    boot=np.divide(daily[ix].sum(axis=1),den,out=np.full(B,np.nan),where=den>0)
    lo,hi=np.nanquantile(boot,[.025,.975])
    centered=daily-daily.mean();null=centered[ix].mean(axis=1)
    p=(1+(null>=daily.mean()).sum())/(B+1)
    # Avoid displaying degenerate intervals from one/few observed trades as evidence.
    supported=len(vals)>=30 and int((counts>0).sum())>=20
    if not supported:lo=hi=None;p=1.
    return {'trades':len(vals),'win_rate':float((vals>0).mean()),'avg_R':float(vals.mean()),'total_R':float(vals.sum()),
            'PF':float(gains/loss) if loss else None,'drawdown_R':float(np.max(np.maximum.accumulate(eq)-eq)),
            'ci_low':float(lo) if lo is not None else None,'ci_high':float(hi) if hi is not None else None,'day_mean_R':float(daily.mean()),'p_boot_one_sided':float(p),
            'median_cost_R':float(trades.roundtrip_cost_R.median()),'mean_hold_minutes':float(trades.hold_minutes.mean()),
            'data_gap_exits':int(trades.exit_reason.str.contains('data_gap|data_end').sum())}

def bh_adjust(p):
    p=np.asarray(p);order=np.argsort(p);ranked=p[order]*len(p)/np.arange(1,len(p)+1)
    q=np.minimum.accumulate(ranked[::-1])[::-1].clip(max=1);out=np.empty(len(p));out[order]=q;return out

def run(data_dir,out_dir,revision='strict',splits=None):
    splits=splits or CONFIG['split_dates']
    train_end=splits['development_end'];val_end=splits['validation_end'];test_end=splits['evaluation_end']
    if not train_end<val_end<test_end:raise ValueError('Require development_end < validation_end < evaluation_end')
    val_start=(pd.Timestamp(train_end)+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    test_start=(pd.Timestamp(val_end)+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    out_dir.mkdir(parents=True,exist_ok=True);summaries=[];all_trades=[];all_candidates=[];qa=[];rejections=[]
    for sym in ['XAUUSD','NDQ','US30']:
        raw=load_data(data_dir/f'{sym}.csv');cache={}
        local=raw.index.tz_convert(NY);sessiondays=sorted(set(str(x) for x in local[local.weekday<5].date))
        gap=(raw.index.to_series().diff()>pd.Timedelta(minutes=1)).sum()
        qa.append({'symbol':sym,'bars':len(raw),'first':raw.index[0].isoformat(),'last':raw.index[-1].isoformat(),
                   'gaps_over_one_minute':int(gap),'zero_volume_bars':int((raw.volume==0).sum()),
                   'sha256':hashlib.sha256((data_dir/f'{sym}.csv').read_bytes()).hexdigest()})
        for spec in [s for s in CONFIG['strategies'] if s['symbol']==sym]:
            candidates,d=generate_candidates(raw,spec,cache,revision)
            for q in candidates:all_candidates.append({'id':spec['id'],**q})
            warm=d.loc[d.h1_ok].index.min();startday=str(warm.tz_convert(NY).date()) if pd.notna(warm) else '9999'
            for volume in [True,False]:
                for cost in [1.,1.5,2.]:
                    tr,rej=simulate(raw,candidates,d,spec,cost,volume)
                    rejections.append({'id':spec['id'],'volume_filter':volume,'cost_mult':cost,**rej})
                    if len(tr):all_trades.append(tr)
                    for segment,lower,upper in [('all',startday,test_end),('development',startday,train_end),('validation',val_start,val_end),('evaluation',test_start,test_end)]:
                        days=[x for x in sessiondays if lower<=x<=upper]
                        sub=tr.loc[(tr.day>=lower)&(tr.day<=upper)] if len(tr) else tr
                        summaries.append({'id':spec['id'],'symbol':sym,'family':spec['family'],'category':spec['category'],'tf':spec['tf'],
                                          'volume_filter':volume,'cost_mult':cost,'segment':segment,'sessions':len(days),'warmup_end':startday,**metrics(sub,days)})
            print(spec['id'],'candidates',len(candidates),flush=True)
    summary=pd.DataFrame(summaries)
    # Primary 15 comparisons; exploratory volume-off variants are separately corrected across 30.
    summary['q_primary_15']=np.nan;summary['q_with_ablation_30']=np.nan
    for segment in summary.segment.unique():
        base=(summary.cost_mult==1)&(summary.segment==segment)
        for col,mask in [('q_primary_15',base&summary.volume_filter),('q_with_ablation_30',base)]:
            summary.loc[mask,col]=bh_adjust(summary.loc[mask,'p_boot_one_sided'])
    summary.to_csv(out_dir/'summary.csv',index=False)
    pd.concat(all_trades,ignore_index=True).to_csv(out_dir/'trades.csv',index=False) if all_trades else (out_dir/'trades.csv').write_text('')
    pd.DataFrame(all_candidates).to_csv(out_dir/'candidates.csv',index=False)
    pd.DataFrame(rejections).fillna(0).to_csv(out_dir/'rejections.csv',index=False)
    (out_dir/'data_quality.json').write_text(json.dumps(qa,indent=2))
    manifest={'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spec_sha256':hashlib.sha256((ROOT/'strategies.json').read_bytes()).hexdigest(),
              'python':__import__('sys').version,'pandas':pd.__version__,'numpy':np.__version__,'data':qa,
              'kind':'preliminary public-vendor historical screening; NOT OANDA validation or live trading',
              'revision':revision,'split_dates':splits,'selection':'No parameter fit. Strict was first screen; simple revision was designed after inspecting strict results. Both are exploratory, not untouched OOS.'}
    (out_dir/'run_manifest.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--data-dir',type=Path,default=ROOT/'data');ap.add_argument('--out-dir',type=Path,default=ROOT/'results');ap.add_argument('--revision',choices=['strict','simple'],default='strict')
    ap.add_argument('--development-end',default=CONFIG['split_dates']['development_end']);ap.add_argument('--validation-end',default=CONFIG['split_dates']['validation_end']);ap.add_argument('--evaluation-end',default=CONFIG['split_dates']['evaluation_end'])
    args=ap.parse_args();run(args.data_dir,args.out_dir,args.revision,{'development_end':args.development_end,'validation_end':args.validation_end,'evaluation_end':args.evaluation_end})
