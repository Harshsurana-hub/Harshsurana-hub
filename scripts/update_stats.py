"""Generate pixel cards from public GitHub data. No third-party stats service."""
import argparse, collections, concurrent.futures, datetime as dt, html, json, os, re, subprocess, time
import urllib.request, urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from pixel_art import rect, pixels, svg, text, animate
ROOT=Path(__file__).resolve().parents[1]
USER='Harshsurana-hub'
A=ROOT/'assets'
MINT='#95eacd'; PURPLE='#bca4eb'; BG='#0d1117'; BORDER='#30364e'

def fetch(url,api=False):
    headers={'User-Agent':'Harshsurana-hub-pixel-profile','Accept':'application/vnd.github+json' if api else 'text/html'}
    token=os.environ.get('GH_TOKEN')
    if api and token: headers['Authorization']='Bearer '+token
    for attempt in range(3):
        try:
            if api and not token:
                return json.loads(subprocess.check_output(['gh','api',url.removeprefix('https://api.github.com/')],text=True))
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=40) as response:
                data=response.read().decode()
            return json.loads(data) if api else data
        except Exception:
            if attempt==2:raise
            time.sleep(2**attempt)

def api(path):return fetch('https://api.github.com/'+path,True)
def pages(path):
    data=[];page=1
    while True:
        batch=api(path+('&' if '?' in path else '?')+f'per_page=100&page={page}')
        data.extend(batch)
        if len(batch)<100:return data
        page+=1

class Calendar(HTMLParser):
    def __init__(self):super().__init__();self.days={};self.tips={};self.current=None;self.parts=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='td' and a.get('data-date'):
            self.days[a['id']]={'date':a['data-date'],'level':int(a['data-level'])}
        if tag=='tool-tip':self.current=a.get('for');self.parts=[]
    def handle_data(self,data):
        if self.current:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='tool-tip' and self.current:
            self.tips[self.current]=''.join(self.parts);self.current=None
    def result(self):
        result=[]
        for key,d in self.days.items():
            tip=self.tips.get(key,''); count=re.match(r'([\d,]+) contribution',tip.strip())
            if not count and not tip.strip().startswith('No contributions'):raise ValueError('Unknown contribution tooltip format')
            result.append({**d,'count':int(count.group(1).replace(',','')) if count else 0})
        if len(result)<350:raise ValueError('Contribution calendar missing or incomplete')
        return sorted(result,key=lambda d:d['date'])

def collect():
    profile=api('users/'+USER)
    repos=pages(f'users/{USER}/repos?type=owner')
    repos=[r for r in repos if not r['private']]
    owned=[r for r in repos if not r['fork']]
    def lang(repo):return api(f"repos/{USER}/{repo['name']}/languages")
    language=collections.Counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(lang,owned):language.update(result)
    counts={}
    for key,query in [('prs','is:pr'),('merged','is:pr is:merged'),('issues','is:issue')]:
        q=urllib.parse.urlencode({'q':f'author:{USER} is:public {query}','per_page':1})
        counts[key]=api('search/issues?'+q)['total_count']
    calendar=Calendar();calendar.feed(fetch(f'https://github.com/users/{USER}/contributions'))
    return {'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'followers':profile['followers'],'repos':len(repos),'stars':sum(r['stargazers_count'] for r in owned),
            **counts,'languages':dict(language),'days':calendar.result()}

def streaks(days):
    best=run=0;best_end=None
    for day in days:
        run=run+1 if day['count'] else 0
        if run>best:best=run;best_end=day['date']
    active=list(days)
    if active and not active[-1]['count']:active.pop() # today's day is still open
    current=0
    for day in reversed(active):
        if not day['count']:break
        current+=1
    return current,best,best_end

def card_shell(h,label,subtitle):
    return [rect(0,0,1200,h,BG),rect(0,0,1200,2,BORDER),rect(0,h-2,1200,2,BORDER),
            pixels(label,28,26,2.5,PURPLE),text(28,78,subtitle,17,'#8793aa')]

def render(d):
    A.mkdir(exist_ok=True)
    stamp=d['generated_at'][:10]
    days=d['days'];total=sum(x['count'] for x in days)
    p=card_shell(326,'PLAYER STATS','PUBLIC GITHUB ACTIVITY / updated '+stamp+' UTC')
    values=[('CONTRIBUTIONS',total,'last 365 days'),('PULL REQUESTS',d['prs'],'public / all time'),('MERGED PRS',d['merged'],'public / all time'),('ISSUES OPENED',d['issues'],'public / all time'),('PUBLIC REPOS',d['repos'],'owned / includes forks'),('STARS EARNED',d['stars'],'owned / excludes forks'),('FOLLOWERS',d['followers'],'current count'),('ACTIVE DAYS',sum(x['count']>0 for x in days),'last 365 days')]
    for i,(label,value,note) in enumerate(values):
        x=28+(i%4)*296;y=98+(i//4)*108
        p.extend([rect(x,y,278,92,'#151b29'),pixels(label,x+14,y+13,1.7,'#a8b1c8'),pixels(str(value),x+14,y+37,4,MINT),text(x+108,y+64,note,12,'#8793aa')])
    (A/'overview.svg').write_text(svg(1200,326,''.join(p),'GitHub public stats: '+', '.join(f'{v} {l.lower()}' for l,v,n in values)))
    current,best,best_end=streaks(days)
    p=card_shell(220,'STREAK CHECKPOINTS','CONSECUTIVE CONTRIBUTION DAYS / rolling public calendar')
    for x,label,value,detail in [(28,'CURRENT STREAK',current,'Today or yesterday is active' if current else 'No active streak today'),(422,'LONGEST STREAK',best,'Within the last 365 days'),(816,'BEST DAY',max(x['count'] for x in days),'Contributions in one day')]:
        p.extend([pixels(label,x,110,2,'#adb4cc'),pixels(str(value),x,142,5,MINT),text(x+100,171,'DAYS' if 'STREAK' in label else 'CONTRIBS',18,PURPLE),text(x,202,detail,15,'#8793aa')])
    (A/'streak.svg').write_text(svg(1200,220,''.join(p),f'Current streak {current} days. Longest streak in the last 365 days {best} days.'))
    p=card_shell(278,'LANGUAGE INVENTORY','CODE BYTES IN PUBLIC OWNED REPOS / excludes forks and Jupyter notebooks')
    langs=sorted([(k,v) for k,v in d['languages'].items() if k!='Jupyter Notebook' and v>0],key=lambda x:-x[1]);totalbytes=sum(v for k,v in langs)
    shown=langs[:6]
    if len(langs)>6:shown.append(('Other',sum(v for k,v in langs[6:])))
    colors=[MINT,PURPLE,'#7fb0f4','#ffc285','#ec9acb','#a8d77a','#67748d'];x=28
    if not shown:p.append(text(28,150,'No public language data yet.',20))
    for i,(name,count) in enumerate(shown):
        w=1144*count/totalbytes;p.append(rect(x,104,w,20,colors[i]));x+=w
        xx=28+(i%3)*392;yy=164+(i//3)*38
        p.extend([rect(xx,yy-11,10,10,colors[i]),text(xx+22,yy,f'{name}  {count/totalbytes:.1%}',17)])
    (A/'languages.svg').write_text(svg(1200,278,''.join(p),'Language distribution by code bytes in public owned repositories, excluding forks and notebooks.'))
    p=card_shell(300,'CONTRIBUTION WORLD',f'{total} contributions / {days[0]["date"]} to {days[-1]["date"]}')
    start=dt.date.fromisoformat(days[0]['date']);offset=(start.weekday()+1)%7
    palette=['#1c2435','#304d51','#43776d','#69b29a',MINT]
    for i,day in enumerate(days):
        n=i+offset;xx=30+(n//7)*21.5;yy=110+(n%7)*21
        p.append(f'<g><title>{day["date"]}: {day["count"]} contributions</title>'+rect(xx,yy,17,17,palette[day['level']])+'</g>')
    p.extend([text(30,280,'LESS',14,'#8793aa'),text(210,280,'MORE',14,'#8793aa'),text(780,280,'ONE PIXEL. ONE CONTRIBUTION.',14,'#8793aa')])
    for i,c in enumerate(palette):p.append(rect(78+i*24,268,16,16,c))
    # A traveling spark decorates the calendar without changing activity data.
    p.append('<rect x="30" y="94" width="8" height="4" fill="'+MINT+'">'+animate('x','30;1150;30','18s')+'</rect>')
    (A/'activity.svg').write_text(svg(1200,300,''.join(p),f'Contribution calendar showing {total} contributions in the last 365 days.'))
    (A/'public-stats.json').write_text(json.dumps(d,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--from-json',type=Path);args=parser.parse_args()
    data=json.loads(args.from_json.read_text()) if args.from_json else collect()
    render(data)
    print('Updated 4 pixel stats cards from public GitHub data.')
