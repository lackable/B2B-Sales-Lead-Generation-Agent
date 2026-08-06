import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import convert_ticker, fallback_financedatabase_website

def test_convert_ticker_nse():
    yahoo_ticker, symbol, suffix = convert_ticker("NSE:TCS")
    assert yahoo_ticker == "TCS.NS"
    assert symbol == "TCS"
    assert suffix == ".NS"

def test_convert_ticker_bse():
    yahoo_ticker, symbol, suffix = convert_ticker("BSE:TCS")
    assert yahoo_ticker == "TCS.BO"
    assert symbol == "TCS"
    assert suffix == ".BO"

def test_convert_ticker_none_and_empty():
    assert convert_ticker(None) == ("", "", "")
    assert convert_ticker("") == ("", "", "")

if __name__ == "__main__":
    test_convert_ticker_nse()
    test_convert_ticker_bse()
    test_convert_ticker_none_and_empty()
    print("✅ All ticker conversion tests passed!")
