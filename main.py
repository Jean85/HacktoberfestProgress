import requests
from flask import Flask, render_template, request, redirect, session
from collections import namedtuple
from flask.ext.session import Session

app = Flask(__name__)
app.config.from_pyfile('config.py')

Session(app)  # set up server-side sessions

client_id = app.config.get('GITHUB_CLIENT_ID')
client_secret = app.config.get('GITHUB_CLIENT_SECRET')

api_base = 'https://api.github.com'

auth_url = 'https://github.com/login/oauth/authorize'\
    '?client_id={}'.format(client_id)

time_range = '2016-10-01T00:00:01Z..2016-10-31T23:59:59'
search_query = 'type:pr+created:' + time_range + '+author:{}'

PullRequest = namedtuple('PullRequest', [
    'url', 'title', 'repo_url', 'repo_name', 'repo_owner'])


def headers(token):
    '''
    Build authentication-headers with `token`
    '''
    return {
        'Authorization': 'token {}'.format(token),
        'User-Agent': 'HacktoberfestProgress/Thor77'
    }


def fetch_login(token):
    '''
    Fetch login-name for user authenticated by `token`
    '''
    r = requests.get(api_base + '/user', headers=headers(token))
    if r.status_code != 200:
        return None
    return r.json()['login']


def fetch_pull_requests(token, username):
    '''
    Fetch pull requests for `username`, authenticated by `token`
    '''
    # requests would urlencode the query so we fill it with a placeholder
    params = {
        'sort': 'created',
        'q': 'QUERY'
    }
    req = requests.Request('GET', api_base + '/search/issues', params=params,
                           headers=headers(token))
    prepared = req.prepare()
    # replace placeholder with actual query
    prepared.url = prepared.url.replace('QUERY', search_query.format(username))
    # send request
    r = requests.Session().send(prepared)
    if r.status_code != 200:
        return []
    return r.json()['items']


@app.route('/')
def index():
    if 'access_token' in session:
        return render_template('index.jinja2')
    else:
        return render_template('index.jinja2', auth_url=auth_url)


@app.route('/auth')
def auth():
    if 'access_token' in session:
        return redirect('/progress')
    if request.args.get('error'):
        return render_template('error.jinja2',
                               error_code=request.args['error'],
                               error_desc=request.args['error_description'],
                               error_uri=request.args['error_uri'])
    elif request.args.get('code'):
        # obtain access_token
        payload = {
            'code': request.args['code'],
            'client_id': client_id,
            'client_secret': client_secret
        }
        headers = {'Accept': 'application/json'}
        r = requests.post('https://github.com/login/oauth/access_token',
                          data=payload, headers=headers).json()
        if 'error' in r:
            return render_template('error.jinja2')
        elif 'access_token' in r:
            session['access_token'] = r['access_token']
            return redirect('/progress')
    return render_template('progress.jinja2')


@app.route('/progress')
def progress():
    if 'access_token' not in session:
        return redirect('/')
    access_token = session.get('access_token')
    # obtain username
    username = fetch_login(access_token)
    raw_pull_requests = fetch_pull_requests(access_token, username)

    pull_requests = []
    for pr in raw_pull_requests:
        # fetch details about pull request
        details_r = requests.get(pr['url'])
        if details_r.status_code != 200:
            return render_template('error.jinja2')
        details = details_r.json()
        # fetch details about repo
        repo_r = requests.get(details['repository_url'])
        if repo_r.status_code != 200:
            return render_template('error.jinja2')
        repo = repo_r.json()
        pull_requests.append(
            PullRequest(
                url=pr['html_url'], title=pr['title'],
                repo_name=repo['name'],
                repo_url=repo['html_url'],
                repo_owner=repo['owner']['login']
            )
        )
    return render_template('progress.jinja2', pull_requests=pull_requests)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=7777)
