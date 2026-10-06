from nbaprops import bbref

HTML = """<table id="box-GSW-game-basic"><tbody>
<tr><th data-stat="player" data-append-csv="curryst01"><a>Stephen Curry</a></th><td data-stat="mp">34:30</td>
<td data-stat="fga">20</td><td data-stat="fta">5</td><td data-stat="trb">6</td><td data-stat="tov">3</td><td data-stat="pts">31</td></tr>
<tr class="thead"><th data-stat="reserver">Reserves</th></tr>
<tr><th data-stat="player" data-append-csv="x01"><a>X Y</a></th><td data-stat="reason">Did Not Play</td></tr>
</tbody></table>"""


def test_boxscore_url_uses_eastern_date_and_bbref_code():
    # 00:30 UTC on 16 Mar is the evening of 15 Mar in New York
    assert bbref.boxscore_url("2026-03-16T00:30Z", "GS").endswith("/boxscores/202603150GSW.html")


def test_parse_boxscore():
    rows = bbref.parse_boxscore(HTML, "GS")
    assert len(rows) == 2
    assert rows[0] == {"player": "Stephen Curry", "slug": "curryst01", "dnp": False, "min": 34.5,
                       "pts": 31, "reb": 6, "fga": 20, "fta": 5, "tov": 3}
    assert rows[1]["dnp"] and rows[1]["min"] == 0
