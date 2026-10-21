"""Raw FortiSIEM clauses get the same attribute aliasing as the dict form.

Live: 4 of 5 `siem_search(by="raw")` calls in a row 400'd. Probing one
attribute per query on the box: dstIpAddr, srcHostName, destHostName and
srcUserName are rejected; destIpAddr, srcName/destName and srcUser/destUser
are the accepted spellings. FortiSIEM's error never names the attribute, so
the model had nothing to correct from.
"""
from fsr_playbooks.mcp_server import tools_triage as T


def test_the_live_failing_clause_is_rewritten_to_accepted_names():
    clause = ('srcIpAddr="10.50.60.70" OR dstIpAddr="10.50.60.70" OR '
              'srcHostName="smithDesktop" OR destHostName="smithDesktop" OR '
              'srcUserName="wendy.smith"')
    out, renamed = T._canon_attrs(clause)
    assert out == ('srcIpAddr="10.50.60.70" OR destIpAddr="10.50.60.70" OR '
                   'srcName="smithDesktop" OR destName="smithDesktop" OR '
                   'srcUser="wendy.smith"')
    assert renamed == {"dstIpAddr": "destIpAddr", "srcHostName": "srcName",
                       "destHostName": "destName", "srcUserName": "srcUser"}


def test_quoted_values_and_accepted_names_are_untouched():
    clause = '(destIpAddr="dstIpAddr=1" AND hostName="srcHostName") OR user="x"'
    out, renamed = T._canon_attrs(clause)
    assert out == clause and renamed == {}


def test_in_and_comparison_operators_are_attribute_positions():
    out, renamed = T._canon_attrs('userName IN ("a","b") AND destIpPort>=443')
    assert out == 'user IN ("a","b") AND destIpPort>=443'
    assert renamed == {"userName": "user"}


def test_raw_query_sends_the_rewritten_clause_and_reports_it(monkeypatch):
    sent = {}

    def fake(where, **kw):
        sent.update(where=where, **kw)
        return {"ok": True, "echo": kw["echo"]}

    monkeypatch.setattr(T, "_siem_pubv2_query", fake)
    res = T.siem_raw_query(where='dstIpAddr="1.2.3.4"',
                           select="phRecvTime,dstIpAddr,srcHostName", window="1h")
    assert sent["where"] == 'destIpAddr="1.2.3.4"'
    assert sent["select"] == "phRecvTime,destIpAddr,srcName"
    assert res["echo"]["renamed_attributes"] == {
        "dstIpAddr": "destIpAddr", "srcHostName": "srcName"}


def test_a_clean_clause_reports_no_renames(monkeypatch):
    monkeypatch.setattr(T, "_siem_pubv2_query",
                        lambda where, **kw: {"ok": True, "echo": kw["echo"]})
    res = T.siem_raw_query(where='srcIpAddr="1.2.3.4"', window="1h")
    assert "renamed_attributes" not in res["echo"]
