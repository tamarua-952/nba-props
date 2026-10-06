# Step 0 source report — github-actions

Run at 2026-10-06 01:44 UTC. 6/20 checks OK.

| Category | Source | Status | Secs | Detail |
|---|---|---|---|---|
| Game logs | nba_api LeagueGameLog 2025-26 (all players, 1 call) | FAIL | 30.5 | requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='stats.nba.com', port=443): Read timed out. (read timeout=30) |
| Game logs | nba_api LeagueGameLog 2024-25 | FAIL | 30.2 | requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='stats.nba.com', port=443): Read timed out. (read timeout=30) |
| Game logs | nba_api PlayerGameLog | FAIL | 30.1 | requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='stats.nba.com', port=443): Read timed out. (read timeout=30) |
| Game logs | nba_api team pace (Advanced) | FAIL | 30.2 | requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='stats.nba.com', port=443): Read timed out. (read timeout=30) |
| Game logs | nba_api PlayerIndex (positions) | FAIL | 30.1 | requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='stats.nba.com', port=443): Read timed out. (read timeout=30) |
| Game logs | NBA CDN box score JSON | FAIL | 0.1 | HTTP 403 from https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json |
| Game logs | ESPN scoreboard + summary box score | OK | 0.3 | 7 games on 2026-03-15; summary has 27 players, stats ['MIN', 'PTS', 'FG', '3PT', 'FT', 'REB'] |
| Game logs | ESPN athlete gamelog | OK | 0.3 | Jokic gamelog: 76 events, labels ['MIN', 'FG', 'FG%', '3PT', '3P%', 'FT'] |
| Game logs | Basketball-Reference player gamelog | OK | 0.2 | HTML 375 KB, ~65 game rows (rate limit: <20 req/min) |
| Schedule | NBA CDN season schedule | FAIL | 0.1 | HTTP 403 from https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json |
| Schedule | NBA CDN today's scoreboard | FAIL | 0.1 | HTTP 403 from https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json |
| Schedule | nba_api ScoreboardV3 today | FAIL | 30.2 | requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='stats.nba.com', port=443): Read timed out. (read timeout=30) |
| Schedule | ESPN scoreboard today/tomorrow (+spreads) | OK | 0.3 | 2026-10-06: 4 games; 2026-10-07: 5 games; 3 with spread/total attached |
| Injuries | Official NBA injury report (PDF) | FAIL | 1.1 | AssertionError: no PDF links on ['https://official.nba.com/nba-injury-report-2026-27-season/', 'https://official.nba.com/nba-injury-report-2025-26-season/'] |
| Injuries | ESPN injuries JSON | OK | 0.1 | 27 teams, 92 injury entries; e.g. Aaron Wiggins: Day-To-Day |
| Injuries | ESPN injuries HTML page | OK | 0.1 | HTML 0 KB, ~0 table rows |
| Consensus lines | The Odds API (free tier) | SKIP | 0.0 | ODDS_API_KEY not set (free tier: 500 credits/month at the-odds-api.com) |
| Consensus lines | ESPN core API propBets | FAIL | 0.6 | AssertionError: event 401901820 (2026-10-06): providers ['100'] have no propBets |
| Consensus lines | PrizePicks public API | FAIL | 0.1 | HTTP 403 from https://api.prizepicks.com/projections?league_id=7&per_page=250&single_stat=true |
| Consensus lines | Underdog public API | FAIL | 0.2 | HTTP 426 from https://api.underdogfantasy.com/beta/v5/over_under_lines |
