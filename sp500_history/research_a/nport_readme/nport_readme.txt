
=== page 1
NPORT Data Sets 
• 1 Overview 
• 2 Scope 
• 3 Organization 
• 4 File Format 
• 5 Table Definitions  
o 5.1 SUBMISSION (Items A.3-4) 
o 5.2 REGISTRANT (Item A.1) 
o 5.3 FUND_REPORTED_INFO (Items A.2, B.1-B.6) 
o 5.4 INTEREST_RATE_RISK (Item B.3.a-b) 
o 5.5 BORROWER (Item B.4.a) 
o 5.6 BORROW_AGGREGATE (Item B.4.b) 
o 5.7 MONTHLY_TOTAL_RETURN (Items B.5.a-b) 
o 5.8 MONTHLY_RETURN_CAT_INSTRUMENT (Item B.5.c) 
o 5.9 FUND_VAR_INFO (Item B.10.b) 
o 5.10 FUND_REPORTED_HOLDING (Items C.1 - C.8, C.11) 
o 5.11 IDENTIFIERS (Item C.1.e) 
o 5.12 DEBT_SECURITY (Item C.9) 
o 5.13 DEBT_SECURITY_REF_INSTRUMENT (Item C.9.f.iii) 
o 5.14 CONVERTIBLE_SECURITY_CURRENCY (Item C.9.f.iv) 
o 5.15 REPURCHASE_AGREEMENT (Item C.10.a-e) 
o 5.16 REPURCHASE_COUNTERPARTY (Item C.10.b.ii) 
o 5.17 REPURCHASE_COLLATERAL (Item C.10.f) 
o 5.18 DERIVATIVE_COUNTERPARTY (Item C.11.b.i) 
o 5.19 SWAPTION_OPTION_WARNT_DERIV (Item C.11.c.i-ii, iv-vi, viii) 
o 5.20 DESC_REF_INDEX_BASKET (Item C.11.c.iii.2) 
o 5.21 DESC_REF_INDEX_COMPONENT (Item C.11.c.iii.2) 
o 5.22 DESC_REF_OTHER (Item C.11.c.iii.3) 
o 5.23 FUT_FWD_NONFOREIGNCUR_CONTRACT (Item C.11.d) 
o 5.24 FWD_FOREIGNCUR_CONTRACT_SWAP (Item C.11.e) 
o 5.25 NONFOREIGN_EXCHANGE_SWAP (Item C.11.f) 
o 5.26 FLOATING_RATE_RESET_TENOR (Item C.11.f.i) 
=== page 2
o 5.27 OTHER_DERIV (Item C.11.g) 
o 5.28 OTHER_DERIV_NOTIONAL_AMOUNT (Item C.11.g.iii) 
o 5.29 SECURITIES_LENDING (Item C.12) 
o 5.30 EXPLANATORY_NOTE (Item E) 
1. Overview 
Form N-PORT is used by registered investment companies and exchange-traded funds to report monthly portfolio holdings other than 
money market funds. Form N-PORT filings are disseminated quarterly. The NPORT Data Sets provides the portfolio holdings from 
the N-PORT filings that have been disseminated. The NPORT Data Sets are extracted from Form N-PORT eXtensible Markup 
Language (XML) submissions in a flat file format to assist users in more easily constructing the data for analysis. These data sets 
includes any amendments to those submissions. The data has been automatically and directly taken from submissions created by the 
registrants and provided as-filed. The data will be published quarterly. Data contained in documents filed after 5:30pm EST on the last 
business day of the quarter will be included in the next quarterly posting.  
SUBMISSION TYPE DESCRIPTION 
N-PORT-P, NPORT-P/A MONTHLY PORTFOLIO INVESTMENTS REPORT 
2. Scope 
The N-PORT data sets consists of XML data submitted from October 2019 through current period. 
Note EDGAR Technical Specifications provides information on Form N-PORT XML Technical Specifications Document.  
3. Organization 
Note that the data sets include information "as filed" in EDGAR document submissions including amendments of prior submissions. 
Data in this submitted form may contain redundancies, inconsistencies, and discrepancies relative to prior submissions and other 
publication formats. There are up to 30 data files. Each quarterly data set is accompanied by a metadata file conforming to the W3C 
specification for tabular data (https://www.w3.org/TR/2015/REC-tabular-data-model-20151217/) that encodes the following 
information about the data files and their relationships to each other 
=== page 3
1. SUBMISSION Contains information from the EDGAR submission, with each row having the primary key 
ACCESSION_NUMBER. 
2. REGISTRANT Contains information about the registrant, with each row having the primary key ACCESSION_NUMBER. 
3. FUND_REPORTED_INFO Contains information about the fund, with each row having the primary key 
ACCESSION_NUMBER. 
4. INTEREST_RATE_RISK Contains information about interest rate risk, with each row having the primary key 
ACCESSION_NUMBER and INTEREST_RATE_RISK_ID. 
5. BORROWER Information for each borrower in a securities lending transaction, with each row having the primary key 
ACCESSION_NUMBER and BORROWER_ID. 
6. BORROW_AGGREGATE Information for each category of non-cash collateral received for loaned securities, with each 
row having the primary key ACCESSION_NUMBER and BORROW_AGGREGATE_ID. 
7. MONTHLY_TOTAL_RETURN Contains monthly total return information for each of the preceding three months, with 
each row having the primary key ACCESSION_NUMBER and MONTHLY_TOTAL_RETURN_ID. 
8. MONTHLY_RETURN_CAT_INSTRUMENT Contains monthly return information attributable to derivatives for each of 
the preceding three months, with each row having the primary key ACCESSION_NUMBER, ASSET_CAT and 
INSTRUMENT_KIND. 
9. FUND_VAR_INFO Provides the Fund's designated index, with each row having the primary key 
ACCESSION_NUMBER. 
10. FUND_REPORTED_HOLDING Contains information about the holdings of the fund, with each row having the primary 
key ACCESSION_NUMBER and HOLDING_ID. 
11. IDENTIFIERS Contains other identifiers for the holding, with each row having the primary key HOLDING_ID and 
IDENTIFIERS_ID. 
=== page 4
12. DEBT_SECURITY Additional information for debt securities holdings, without primary key. 
13. DEBT_SECURITY_REF_INSTRUMENT The debt securities reference instrument for convertible securities, with each 
row having the primary key HOLDING_ID and DEBT_SECURITY_REF_ID. 
14. CONVERTIBLE_SECURITY_CURRENCY The convertible securities conversion ratio per 1000 units of the relevant 
currency, with each row having the primary key HOLDING_ID and CONVERTIBLE_SECURITY_ID. 
15. REPURCHASE_AGREEMENT Contains information for repurchase and reverse repurchase agreements, with each row 
having the primary key HOLDING_ID. 
16. REPURCHASE_COUNTERPARTY Provides the repurchase and reverse repurchase agreement counterparty, with each 
row having the primary key HOLDING_ID and REPURCHASE_COUNTERPARTY_ID. 
17. REPURCHASE_COLLATERAL Contains information concerning securities subject to repurchase agreement, with each 
row having the primary key HOLDING_ID and REPURCHASE_COLLATERAL_ID. 
18. DERIVATIVE_COUNTERPARTY Provides the derivative instrument counterparty, with each row having the primary 
key HOLDING_ID and DERIVATIVE_COUNTERPARTY_ID. 
19. SWAPTION_OPTION_WARNT_DERIV Contains information about options and warrants, including options on a 
derivative (swaptions), with each row having the primary key HOLDING_ID. 
20. DESC_REF_INDEX_BASKET The index or custom basket reference instrument for options and warrants, including 
options on a derivative (swaptions), with each row having the primary key HOLDING_ID. 
21. DESC_REF_INDEX_COMPONENT The index or custom basket components, with each row having the primary key 
HOLDING_ID and DESC_REF_INDEX_COMPONENT_ID. 
22. DESC_REF_OTHER Information for reference instrument that is not a derivative, index or custom basket, with each row 
having the primary key HOLDING_ID and DESC_REF_OTHER_ID. 
=== page 5
23. FUT_FWD_NONFOREIGNCUR_CONTRACT Contains information for futures and forwards (other than foreign 
currency contracts), with each row having the primary key HOLDING_ID. 
24. FWD_FOREIGNCUR_CONTRACT_SWAP Contains information about forward foreign currency contracts and foreign 
currency swaps, with each row having the primary key HOLDING_ID. 
25. NONFOREIGN_EXCHANGE_SWAP Contains swap information (other than foreign exchange swaps), with each row 
having the primary key HOLDING_ID. 
26. FLOATING_RATE_RESET_TENOR For swaps, the terms of payments paid and received, with each row having the 
primary key HOLDING_ID and RATE_RESET_TENOR_ID. 
27. OTHER_DERIV Contains information for other derivatives, with each row having the primary key HOLDING_ID. 
28. OTHER_DERIV_NOTIONAL_AMOUNT Contains notional amount(s) for other derivatives, with each row having the 
primary key HOLDING_ID and OTHER_DERIV_NOTIONAL_AMOUNT_ID. 
29. SECURITIES_LENDING Contains information for securities lending, with each row having the primary key 
HOLDING_ID. 
30. EXPLANATORY_NOTE Any information provided by the fund in response to an item, with each row having the primary 
key ACCESSION_NUMBER and EXPLANATORY_NOTE_ID. 
4. File Format 
Each of the data file provide text format, tab delimited, UTF-8 encoding.  
5. Table Definitions 
The fields in the tables below provide the following information: field name, description, data format, maximum field size, an 
indication of whether or not the field may be NULL (yes or no), and key. The Key field indicates whether the field is part of a unique 
index on the data. There are two possible values for this field: 
=== page 6
• "*" Indicates the field is part of the unique key for the row. 
• Empty (nothing in field) means the field is not part of the unique compound key. 
5.1 SUBMISSION (Items A.3-4) 
Field Name Description Data Type Nullable Key Item In 
Rule 
ACCESSION_NUMBER 
The 20-character string formed from the 18-digit 
number assigned by the Commission to each EDGAR 
submission. 
VARCHAR2(20) N *  
FILING_DATE Filing date DATE Y   
FILE_NUM File number VARCHAR2(30) Y   
SUB_TYPE NPORT-P, NPORT-P/A, NT NPORT-P VARCHAR2(15) Y   
REPORT_ENDING_PERIOD Date of fiscal year-end DATE Y  A.3.a 
REPORT_DATE Date as of which information is reported DATE Y  A.3.b 
IS_LAST_FILING Does the Fund anticipate that this will be its final filing 
on Form N-PORT CHAR(1) Y  A.4 
5.2 REGISTRANT (Item A.1) 
Field Name Description Data Type Nullable Key Item In 
Rule 
ACCESSION_NUMBER The 20-character string formed from the 18-digit number 
assigned by the Commission to each EDGAR submission. VARCHAR2(20) N *  
CIK CIK number VARCHAR2(10) Y  A.1.c 
REGISTRANT_NAME Name of Registrant VARCHAR2(150) Y  A.1.a 
FILE_NUM Investment Company Act file number VARCHAR2(30) Y  A.1.b 
LEI LEI of Registrant VARCHAR2(20) Y  A.1.d 
=== page 7
Field Name Description Data Type Nullable Key Item In 
Rule 
ADDRESS1 Address line 1 VARCHAR2(40) Y  A.1.e 
ADDRESS2 Address line 2 VARCHAR2(40) Y  A.1.e 
CITY City VARCHAR2(30) Y  A.1.e 
STATE State VARCHAR2(5) Y  A.1.e 
COUNTRY Country VARCHAR2(10) Y  A.1.e 
ZIP Zip code VARCHAR2(10) Y  A.1.e 
PHONE Phone VARCHAR2(20) Y  A.1.e 
5.3 FUND_REPORTED_INFO (Items A.2, B.1-B.6) 
Field Name Description Data Type Nullable Key 
Item 
In 
Rule 
ACCESSION_NUMBER 
The 20-character string formed from the 
18-digit number assigned by the 
Commission to each EDGAR 
submission. 
VARCHAR2(20) N *  
SERIES_NAME Name of Series VARCHAR2(150) Y  A.2.a 
SERIES_ID EDGAR Series Identifier VARCHAR2(10) Y  A.2.b 
SERIES_LEI LEI of Series. VARCHAR2(20) Y  A.2.c 
TOTAL_ASSETS Total assets NUMBER(36,12) Y  B.1.a 
TOTAL_LIABILITIES Total liabilities NUMBER(36,12) Y  B.1.b 
NET_ASSETS Net assets NUMBER(36,12) Y  B.1.c 
ASSETS_ATTRBT_TO_MISC_SECURITY Assets attributable to miscellaneous 
securities NUMBER(36,12) Y  B.2.a 
=== page 8
Field Name Description Data Type Nullable Key 
Item 
In 
Rule 
ASSETS_INVESTED Assets invested in a Controlled Foreign 
Corporation NUMBER(36,12) Y  B.2.b 
BORROWING_PAY_WITHIN_1YR 
Amounts payable to banks or other 
financial institutions for borrowings 
within one year 
NUMBER(36,12) Y  B.2.c 
CTRLD_COMPANIES_PAY_WITHIN_1YR Amounts payable to controlled 
companies within one year NUMBER(36,12) Y  B.2.c 
OTHER_AFFILIA_PAY_WITHIN_1YR Amounts payable to other affiliates 
within one year NUMBER(36,12) Y  B.2.c 
OTHER_PAY_WITHIN_1YR Amounts payable to others within one 
year NUMBER(36,12) Y  B.2.c 
BORROWING_PAY_AFTER_1YR 
Amounts payable to banks or other 
financial institutions for borrowings 
after one year 
NUMBER(36,12) Y  B.2.c 
CTRLD_COMPANIES_PAY_AFTER_1YR Amounts payable to controlled 
companies after one year NUMBER(36,12) Y  B.2.c 
OTHER_AFFILIA_PAY_AFTER_1YR Amounts payable to other affiliates after 
one year NUMBER(36,12) Y  B.2.c 
OTHER_PAY_AFTER_1YR Amounts payable to others after one 
year NUMBER(36,12) Y  B.2.c 
DELAYED_DELIVERY 
Payables for investments purchased on a 
delayed delivery, when-issued, or other 
firm commitment basis 
NUMBER(36,12) Y  B.2.d 
STANDBY_COMMITMENT Payables for investments purchased on a 
standby commitment basis NUMBER(36,12) Y  B.2.d 
=== page 9
Field Name Description Data Type Nullable Key 
Item 
In 
Rule 
LIQUIDATION_PREFERENCE Liquidation preference of outstanding 
preferred stock issued by the Fund NUMBER(36,12) Y  B.2.e 
CASH_NOT_RPTD_IN_C_OR_D Cash and cash equivalents not reported 
in Parts C or D NUMBER(36,12) Y  B.2.f 
CREDIT_SPREAD_3MON_INVEST 
The change in value of the portfolio 
resulting from a 1 basis point change in 
credit spreads where the shift is applied 
to the option adjusted spread, 
aggregated by investment grade for 3 
month maturity 
NUMBER(36,12) Y  B.3.c 
CREDIT_SPREAD_1YR_INVEST 
The change in value of the portfolio 
resulting from a 1 basis point change in 
credit spreads where the shift is applied 
to the option adjusted spread, 
aggregated by investment grade for 1 
year maturity 
NUMBER(36,12) Y  B.3.c 
CREDIT_SPREAD_5YR_INVEST 
The change in value of the portfolio 
resulting from a 1 basis point change in 
credit spreads where the shift is applied 
to the option adjusted spread, 
aggregated by investment grade for 5 
year maturity 
NUMBER(36,12) Y  B.3.c 
CREDIT_SPREAD_10YR_INVEST 
The change in value of the portfolio 
resulting from a 1 basis point change in 
credit spreads where the shift is applied 
to the option adjusted spread, 
aggregated by investment grade for 10 
year maturity 
NUMBER(36,12) Y  B.3.c 
=== page 10
Field Name Description Data Type Nullable Key 
Item 
In 
Rule 
CREDIT_SPREAD_30YR_INVEST 
The change in value of the portfolio 
resulting from a 1 basis point change in 
credit spreads where the shift is applied 
to the option adjusted spread, 
aggregated by investment grade for 30 
year maturity 
NUMBER(36,12) Y  B.3.c 
CREDIT_SPREAD_3MON_NONINVEST 
The change in value of the portfolio 
resulting from a 1 basis point change in 
credit spreads where the shift is applied 
to the option adjusted spread, 
aggregated by non investment grade for 
3 month maturity 
NUMBER(36,12) Y  B.3.c 
CREDIT_SPREAD_1YR_NONINVEST 
The change in value of the portfolio 
resulting from a 1 basis point change in 
credit spreads where the shift is applied 
to the option adjusted spread, 
aggregated by non investment grade for 
1 year maturity 
NUMBER(36,12) Y  B.3.c 
CREDIT_SPREAD_5YR_NONINVEST 
The change in value of the portfolio 
resulting from a 1 basis point change in 
credit spreads where the shift is applied 
to the option adjusted spread, 
aggregated by non investment grade for 
5 year maturity 
NUMBER(36,12) Y  B.3.c 
CREDIT_SPREAD_10YR_NONINVEST 
The change in value of the portfolio 
resulting from a 1 basis point change in 
credit spreads where the shift is applied 
to the option adjusted spread, 
NUMBER(36,12) Y  B.3.c 
=== page 11
Field Name Description Data Type Nullable Key 
Item 
In 
Rule 
aggregated by non investment grade for 
10 year maturity 
CREDIT_SPREAD_30YR_NONINVEST 
The change in value of the portfolio 
resulting from a 1 basis point change in 
credit spreads where the shift is applied 
to the option adjusted spread, 
aggregated by non investment grade for 
30 year maturity 
NUMBER(36,12) Y  B.3.c 
IS_NON_CASH_COLLATERAL Did any securities lending counterparty 
provide any non-cash collateral CHAR(1) Y  B.4.b 
NET_REALIZE_GAIN_NONDERIV_MON1 
First month net realized gain (loss) 
attributable to investments other than 
derivatives 
NUMBER(36,12) Y  B.5.d 
NET_UNREALIZE_AP_NONDERIV_MON1 
First month net change in unrealized 
appreciation (or depreciation) 
attributable to investments other than 
derivatives 
NUMBER(36,12) Y  B.5.d 
NET_REALIZE_GAIN_NONDERIV_MON2 
Second month net realized gain (loss) 
attributable to investments other than 
derivatives 
NUMBER(36,12) Y  B.5.d 
NET_UNREALIZE_AP_NONDERIV_MON2 
Second month net change in unrealized 
appreciation (or depreciation) 
attributable to investments other than 
derivatives 
NUMBER(36,12) Y  B.5.d 
NET_REALIZE_GAIN_NONDERIV_MON3 
Third month net realized gain (loss) 
attributable to investments other than 
derivatives 
NUMBER(36,12) Y  B.5.d 
=== page 12
Field Name Description Data Type Nullable Key 
Item 
In 
Rule 
NET_UNREALIZE_AP_NONDERIV_MON3 
Third month net change in unrealized 
appreciation (or depreciation) 
attributable to investments other than 
derivatives 
NUMBER(36,12) Y  B.5.d 
SALES_FLOW_MON1 First Month Total net asset value of 
shares sold NUMBER(36,12) Y  B.6.a 
REINVESTMENT_FLOW_MON1 
First Month Total net asset value of 
shares sold in connection with 
reinvestments of dividends and 
distributions 
NUMBER(36,12) Y  B.6.b 
REDEMPTION_FLOW_MON1 
First Month Total net asset value of 
shares redeemed or repurchased, 
including exchanges 
NUMBER(36,12) Y  B.6.c 
SALES_FLOW_MON2 Second Month Total net asset value of 
shares sold NUMBER(36,12) Y  B.6.a 
REINVESTMENT_FLOW_MON2 
Second Month Total net asset value of 
shares sold in connection with 
reinvestments of dividends and 
distributions 
NUMBER(36,12) Y  B.6.b 
REDEMPTION_FLOW_MON2 
Second Month Total net asset value of 
shares redeemed or repurchased, 
including exchanges 
NUMBER(36,12) Y  B.6.c 
SALES_FLOW_MON3 Third Month Total net asset value of 
shares sold NUMBER(36,12) Y  B.6.a 
REINVESTMENT_FLOW_MON3 Third Month Total net asset value of 
shares sold in connection with NUMBER(36,12) Y  B.6.b 
=== page 13
Field Name Description Data Type Nullable Key 
Item 
In 
Rule 
reinvestments of dividends and 
distributions 
REDEMPTION_FLOW_MON3 
Third Month Total net asset value of 
shares redeemed or repurchased, 
including exchanges 
NUMBER(36,12) Y  B.6.c 
5.4 INTEREST_RATE_RISK (Item B.3.a-b) 
Field Name Description Data Type Nullable Key Item In 
Rule 
ACCESSION_NUMBER 
The 20-character string formed from 
the 18-digit number assigned by the 
Commission to each EDGAR 
submission. 
VARCHAR2(20) N *  
INTEREST_RATE_RISK_ID Surrogate Key NUMBER(38) N *  
CURRENCY_CODE Currency code VARCHAR2(3) N  B.3.a,B.3.b 
INTRST_RATE_CHANGE_3MON_DV01 
Change in value of the portfolio 
resulting from a 1 basis point change 
in interest rates for maturity in 3 
months 
NUMBER(36,12) Y  B.3.a 
INTRST_RATE_CHANGE_1YR_DV01 
Change in value of the portfolio 
resulting from a 1 basis point change 
in interest rates for maturity in 1 year 
NUMBER(36,12) Y  B.3.a 
INTRST_RATE_CHANGE_5YR_DV01 
Change in value of the portfolio 
resulting from a 1 basis point change 
in interest rates for maturity in 5 years 
NUMBER(36,12) Y  B.3.a 
=== page 14
Field Name Description Data Type Nullable Key Item In 
Rule 
INTRST_RATE_CHANGE_10YR_DV01 
Change in value of the portfolio 
resulting from a 1 basis point change 
in interest rates for maturity in 10 
years 
NUMBER(36,12) Y  B.3.a 
INTRST_RATE_CHANGE_30YR_DV01 
Change in value of the portfolio 
resulting from a 1 basis point change 
in interest rates for maturity in 30 
years 
NUMBER(36,12) Y  B.3.a 
INTRST_RATE_CHANGE_3MON_DV100 
Change in value of the portfolio 
resulting from a 100 basis point 
change in interest rates for maturity in 
3 months 
NUMBER(36,12) Y  B.3.b 
INTRST_RATE_CHANGE_1YR_DV100 
Change in value of the portfolio 
resulting from a 100 basis point 
change in interest rates for maturity in 
1 year 
NUMBER(36,12) Y  B.3.b 
INTRST_RATE_CHANGE_5YR_DV100 
Change in value of the portfolio 
resulting from a 100 basis point 
change in interest rates for maturity in 
5 years 
NUMBER(36,12) Y  B.3.b 
INTRST_RATE_CHANGE_10YR_DV100 
Change in value of the portfolio 
resulting from a 100 basis point 
change in interest rates for maturity in 
10 years 
NUMBER(36,12) Y  B.3.b 
INTRST_RATE_CHANGE_30YR_DV100 
Change in value of the portfolio 
resulting from a 100 basis point 
change in interest rates for maturity in 
30 years 
NUMBER(36,12) Y  B.3.b 
=== page 15
5.5 BORROWER (Item B.4.a) 
Field Name Description Data Type Nullable Key Item In 
Rule 
ACCESSION_NUMBER The 20-character string formed from the 18-digit number 
assigned by the Commission to each EDGAR submission. VARCHAR2(20) N *  
BORROWER_ID Surrogate Key NUMBER(38) N *  
NAME Name of borrower VARCHAR2(150) Y  B.4.a.i 
LEI LEI (if any) of borrower. VARCHAR2(20) Y  B.4.a.ii 
AGGREGATE_VALUE Aggregate value of all securities on loan to the borrower. NUMBER(36,12) Y  B.4.a.iii 
5.6 BORROW_AGGREGATE (Item B.4.b) 
Field Name Description Data Type Nullable Key Item In 
Rule 
ACCESSION_NUMBER 
The 20-character string formed from the 18-digit 
number assigned by the Commission to each EDGAR 
submission. 
VARCHAR2(20) N *  
BORROW_AGGREGATE_ID Surrogate Key NUMBER(38) N *  
AMOUNT Aggregate principal amount NUMBER(36,12) Y  B.4.b.i 
COLLATERAL Aggregate value of collateral NUMBER(36,12) Y  B.4.b.ii 
INVESTMENT_CAT Category of investments VARCHAR2(20) Y  B.4.b.iii 
OTHER_DESC Brief description if category of investment is Other 
Instrument CLOB Y  B.4.b.iii 
5.7 MONTHLY_TOTAL_RETURN (Items B.5.a-b) 
=== page 16
Field Name Description Data Type Nullable Key Item In 
Rule 
ACCESSION_NUMBER 
The 20-character string formed from the 18-digit 
number assigned by the Commission to each 
EDGAR submission. 
VARCHAR2(20) N *  
MONTHLY_TOTAL_RETURN_ID Surrogate Key NUMBER(38) N *  
CLASS_ID Class identification number(s) (if any) of the 
Class(es) for which returns are reported. VARCHAR2(10) Y  B.5.b 
MONTHLY_TOTAL_RETURN1 First Month total returns of the Fund NUMBER(36,12) Y  B.5.a 
MONTHLY_TOTAL_RETURN2 Second Month total returns of the Fund NUMBER(36,12) Y  B.5.a 
MONTHLY_TOTAL_RETURN3 Third Month total returns of the Fund NUMBER(36,12) Y  B.5.a 
5.8 MONTHLY_RETURN_CAT_INSTRUMENT (Item B.5.c) 
Field Name Description Data Type Nullable Key Item In 
Rule 
ACCESSION_NUMBER 
The 20-character string formed from the 18-digit 
number assigned by the Commission to each 
EDGAR submission. 
VARCHAR2(20) N *  
ASSET_CAT Asset category VARCHAR2(30) Y * B.5.c 
INSTRUMENT_KIND 
From each asset category further breakdown by 
derivatives instrument: forward, future, option, 
swaption, swap, warrant, and other 
VARCHAR2(30) Y * B.5.c 
NET_REALIZED_GAIN_MON1 First month net realized gain (loss) attributable to 
derivatives NUMBER(36,12) Y  B.5.c 
NET_UNREALIZED_AP_MON1 First month net change in unrealized appreciation (or 
depreciation) attributable to derivatives NUMBER(36,12) Y  B.5.c 
=== page 17
Field Name Description Data Type Nullable Key Item In 
Rule 
NET_REALIZED_GAIN_MON2 Second month net realized gain (loss) attributable to 
derivatives NUMBER(36,12) Y  B.5.c 
NET_UNREALIZED_AP_MON2 Second month net change in unrealized appreciation 
(or depreciation) attributable to derivatives NUMBER(36,12) Y  B.5.c 
NET_REALIZED_GAIN_MON3 Third month net realized gain (loss) attributable to 
derivatives NUMBER(36,12) Y  B.5.c 
NET_UNREALIZED_AP_MON3 Third month net change in unrealized appreciation 
(or depreciation) attributable to derivatives NUMBER(36,12) Y  B.5.c 
5.9 FUND_VAR_INFO (Item B.10.b) 
Field Name Description Data Type Nullable Key Item In 
Rule 
ACCESSION_NUMBER 
The 20-character string formed from the 18-
digit number assigned by the Commission to 
each EDGAR submission. 
VARCHAR2(20) N *  
DESIGNATED_INDEX_NAME 
For Funds subject to Relative VaR Test 
during the period, the name of the Fund's 
Designated Index, or a statement that the 
Fund's Designated Reference Portfolio is the 
Fund's Securities Portfolio 
VARCHAR2(250) Y  B.10.b.i 
DESIGNATED_INDEX_IDENTIFIER The index identifier for the Fund's 
Designated Index. VARCHAR2(150) Y  B.10.b.ii 
5.10 FUND_REPORTED_HOLDING (Items C.1 - C.8, C.11) 
=== page 18
Field Name Description Data Type Nullable Key Item In 
Rule 
ACCESSION_NUMBER 
The 20-character string formed from the 18-digit 
number assigned by the Commission to each 
EDGAR submission. 
VARCHAR2(20) N *  
HOLDING_ID Surrogate Key NUMBER(38) N *  
ISSUER_NAME Name of issuer VARCHAR2(150) Y  C.1.a 
ISSUER_LEI 
LEI (if any) of issuer. In the case of a holding in a 
fund that is a series of a series trust, report the LEI of 
the series 
VARCHAR2(20) Y  C.1.b 
ISSUER_TITLE Title of the issue or description of the investment. VARCHAR2(150) Y  C.1.c 
ISSUER_CUSIP CUSIP VARCHAR2(9) Y  C.1.d 
BALANCE Balance NUMBER(36,12) Y  C.2.a 
UNIT Indicate whether balance amount is expressed in 
number of shares, principal amount, or other units VARCHAR2(5) Y  C.2.a 
OTHER_UNIT_DESC Other units description VARCHAR2(150) Y  C.2.a 
CURRENCY_CODE Currency code VARCHAR2(3) Y  C.2.b 
CURRENCY_VALUE Value NUMBER(36,12) Y  C.2.c 
EXCHANGE_RATE Exchange rate NUMBER(36,12) Y  C.2.c 
PERCENTAGE Percentage value compared to net assets of the Fund NUMBER(36,12) Y  C.2.d 
PAYOFF_PROFILE Payoff profile -- long, short, N/A VARCHAR2(10) Y  C.3 
ASSET_CAT Asset type VARCHAR2(10) Y  C.4.a 
OTHER_ASSET If Asset type is Other, provide a brief description. VARCHAR2(150) Y  C.4.a 
ISSUER_TYPE Issuer type VARCHAR2(20) Y  C.4.b 
OTHER_ISSUER If Issuer type is Other, provide a brief description. VARCHAR2(150) Y  C.4.b 
INVESTMENT_COUNTRY Report the ISO country code that corresponds to the 
country where the issuer is organized VARCHAR2(10) Y  C.5.a 
=== page 19
Field Name Description Data Type Nullable Key Item In 
Rule 
IS_RESTRICTED_SECURITY Is the investment a Restricted Security CHAR(1) Y  C.6 
FAIR_VALUE_LEVEL The level within the fair value hierarchy in which the 
fair value measurements fall pursuant to US GAAP VARCHAR2(10) Y  C.8 
DERIVATIVE_CAT Type of derivative instrument VARCHAR2(10) Y  C.11.a 
5.11 IDENTIFIERS (Item C.1.e) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of portfolio 
investments NUMBER(38) N *  
IDENTIFIERS_ID Surrogate Key NUMBER(38) N *  
IDENTIFIER_ISIN ISIN VARCHAR2(12) Y  C.1.e.i 
IDENTIFIER_TICKER Ticker VARCHAR2(50) Y  C.1.e.ii 
OTHER_IDENTIFIER Other identifier VARCHAR2(150) Y  C.1.e.iii 
OTHER_IDENTIFIER_DESC Other identifier type used VARCHAR2(150) Y  C.1.e.iii 
5.12 DEBT_SECURITY (Item C.9) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of 
portfolio investments NUMBER(38) N   
MATURITY_DATE Maturity date DATE Y  C.9.a 
=== page 20
Field Name Description Data Type Nullable Key Item In 
Rule 
COUPON_TYPE 
The category that most closely reflects the 
coupon type among the following: fixed, 
floating, variable, none. 
VARCHAR2(10) Y  C.9.b.i 
ANNUALIZED_RATE Annualized rate. NUMBER(36,12) Y  C.9.b.ii 
IS_DEFAULT Currently in default CHAR(1) Y  C.9.c 
ARE_ANY_INTEREST_PAYMENT 
Are there any interest payments in arrears or 
have any coupon payments been legally 
deferred by the issuer 
CHAR(1) Y  C.9.d 
IS_ANY_PORTION_INTEREST_PAID Is any portion of the interest paid in kind? CHAR(1) Y  C.9.e 
IS_CONVTIBLE_MANDATORY Is it Mandatory convertible CHAR(1) Y  C.9.f.i 
IS_CONVTIBLE_CONTINGENT Is it Contingent convertible CHAR(1) Y  C.9.f.ii 
5.13 DEBT_SECURITY_REF_INSTRUMENT (Item C.9.f.iii) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of portfolio 
investments NUMBER(38) N *  
DEBT_SECURITY_REF_ID Surrogate Key NUMBER(38) N *  
ISSUER_NAME Name of issuer VARCHAR2(150) N  C.9.f.iii 
ISSUE_TITLE Title of issue VARCHAR2(150) N  C.9.f.iii 
CURRENCY_CODE Currency code VARCHAR2(3) N  C.9.f.iii 
CUSIP CUSIP of reference instrument VARCHAR2(9) Y  C.9.f.iii 
ISIN ISIN VARCHAR2(12) Y  C.9.f.iii 
TICKER Ticker VARCHAR2(50) Y  C.9.f.iii 
=== page 21
Field Name Description Data Type Nullable Key Item In 
Rule 
OTHER_IDENTIFIER Other identifier VARCHAR2(150) Y  C.9.f.iii 
OTHER_DESC Type of identifier if 'other' identifier provided VARCHAR2(150) Y  C.9.f.iii 
5.14 CONVERTIBLE_SECURITY_CURRENCY (Item C.9.f.iv) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of 
portfolio investments NUMBER(38) N *  
CONVERTIBLE_SECURITY_ID Surrogate Key NUMBER(38) N *  
CONVERSION_RATIO Conversion ratio NUMBER(36,12) Y  C.9.f.iv 
CURRENCY_CODE Currency code VARCHAR2(3) Y  C.9.f.iv 
5.15 REPURCHASE_AGREEMENT (Item C.10.a-e) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of portfolio 
investments NUMBER(38) N *  
TRANSACTION_TYPE Category that most closely reflects the 
transaction (repurchase, reverse repurchase) VARCHAR2(30) Y  C.10.a 
IS_CLEARED Cleared by central counterparty CHAR(1) Y  C.10.b.i 
CENTRAL_COUNTER_PARTY Name of the central counterparty VARCHAR2(150) Y  C.10.b.i 
IS_TRIPARTY Tri-party CHAR(1) Y  C.10.c 
REPURCHASE_RATE Repurchase rate NUMBER(36,12) Y  C.10.d 
=== page 22
Field Name Description Data Type Nullable Key Item In 
Rule 
MATURITY_DATE Maturity date DATE Y  C.10.e 
5.16 REPURCHASE_COUNTERPARTY (Item C.10.b.ii) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of 
portfolio investments NUMBER(38) N *  
REPURCHASE_COUNTERPARTY_ID Surrogate Key NUMBER(38) N *  
NAME Name of counterparty VARCHAR2(150) Y  C.10.b.ii 
LEI LEI (if any) of counterparty VARCHAR2(20) Y  C.10.b.ii 
5.17 REPURCHASE_COLLATERAL (Item C.10.f) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of 
portfolio investments NUMBER(38) N *  
REPURCHASE_COLLATERAL_ID Surrogate Key NUMBER(38) N *  
PRINCIPAL_AMOUNT Principal amount NUMBER(36,12) Y  C.10.f.i 
PRINCIPAL_CURRENCY_CODE Principal currency code VARCHAR2(3) Y  C.10.f.i 
COLLATERAL_AMOUNT Value of collateral NUMBER(36,12) Y  C.10.f.ii 
COLLATERAL_CURRENCY_CODE Collateral currency code VARCHAR2(3) Y  C.10.f.ii 
INVESTMENT_CAT Category of investments that most closely 
represents the collateral VARCHAR2(20) Y  C.10.f.iii 
=== page 23
Field Name Description Data Type Nullable Key Item In 
Rule 
OTHER_INTRUMENT_DESC Brief description if category of investment 
is Other Instrument VARCHAR2(150) Y  C.10.f.iii 
5.18 DERIVATIVE_COUNTERPARTY (Item C.11.b.i) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of 
portfolio investments NUMBER(38) N *  
DERIVATIVE_COUNTERPARTY_ID Surrogate Key NUMBER(38) N *  
DERIVATIVE_COUNTERPARTY_NAME Name of counterparty CHAR(200) Y  C.11.b.i 
DERIVATIVE_COUNTERPARTY_LEI LEI (if any) of counterparty CHAR(20) Y  C.11.b.i 
5.19 SWAPTION_OPTION_WARNT_DERIV (Item C.11.c.i-ii, iv-vi, viii) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of 
portfolio investments NUMBER(38) N *  
PUT_OR_CALL Type, selected from among the following (put, 
call). Respond call for warrants VARCHAR2(5) Y  C.11.c.i 
WRITTEN_OR_PURCHASED 
Payoff profile, selected from among the 
following (written, purchased). Respond 
purchased for warrants 
VARCHAR2(10) Y  C.11.c.ii 
SHARES_CNT Number of shares of underlying reference 
instrument per contract NUMBER(36,12) Y  C.11.c.iv 
=== page 24
Field Name Description Data Type Nullable Key Item In 
Rule 
PRINCIPAL_AMOUNT Principal amount of underlying reference 
instrument per contract NUMBER(36,12) Y  C.11.c.iv 
CURRENCY_CODE Currency code VARCHAR2(3) Y  C.11.c.iv 
EXERCISE_PRICE Exercise price or rate NUMBER(36,12) Y  C.11.c.v 
EXPIRATION_DATE Expiration date. DATE Y  C.11.c.vi 
UNREALIZED_APPRECIATION 
Unrealized appreciation or depreciation. 
Depreciation shall be reported as a negative 
number 
NUMBER(36,12) Y  C.11.c.viii 
5.20 DESC_REF_INDEX_BASKET (Item C.11.c.iii.2) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of portfolio 
investments NUMBER(38) N *  
INDEX_NAME Index Name VARCHAR2(150) Y  C.11.c.iii.2 
INDEX_IDENTIFIER Index Identifier VARCHAR2(150) Y  C.11.c.iii.2 
NARRATIVE_DESC Narrative Description VARCHAR2(150) Y  C.11.c.iii.2 
5.21 DESC_REF_INDEX_COMPONENT (Item C.11.c.iii.2) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of 
portfolio investments NUMBER(38) N *  
DESC_REF_INDEX_COMPONENT_ID Surrogate Key NUMBER(38) N *  
=== page 25
Field Name Description Data Type Nullable Key Item In 
Rule 
NAME Name of component VARCHAR2(150) Y  C.11.c.iii.2 
CUSIP CUSIP VARCHAR2(9) Y  C.11.c.iii.2 
ISIN ISIN VARCHAR2(12) Y  C.11.c.iii.2 
TICKER Ticker VARCHAR2(50) Y  C.11.c.iii.2 
OTHER_IDENTIFIER Other identifier VARCHAR2(150) Y  C.11.c.iii.2 
OTHER_DESC Other identifier type used VARCHAR2(150) Y  C.11.c.iii.2 
NOTIONAL_AMOUNT Notional amount NUMBER(36,12) Y  C.11.c.iii.2 
CURRENCY_CODE Currency code VARCHAR2(3) Y  C.11.c.iii.2 
VALUE Value NUMBER(36,12) Y  C.11.c.iii.2 
ISSUER_CURRENCY_CODE Currency code of issuer VARCHAR2(3) Y  C.11.c.iii.2 
5.22 DESC_REF_OTHER (Item C.11.c.iii.3) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of portfolio 
investments NUMBER(38) N *  
DESC_REF_OTHER_ID Surrogate Key NUMBER(38) N *  
ISSUER_NAME Issuer name VARCHAR2(150) Y  C.11.c.iii.3 
ISSUE_TITLE Issuer title VARCHAR2(150) Y  C.11.c.iii.3 
CUSIP CUSIP VARCHAR2(9) Y  C.11.c.iii.3 
ISIN ISIN VARCHAR2(12) Y  C.11.c.iii.3 
TICKER Ticker VARCHAR2(50) Y  C.11.c.iii.3 
OTHER_IDENTIFIER Other identifier VARCHAR2(150) Y  C.11.c.iii.3 
=== page 26
Field Name Description Data Type Nullable Key Item In 
Rule 
OTHER_DESC Other identifier type used VARCHAR2(150) Y  C.11.c.iii.3 
5.23 FUT_FWD_NONFOREIGNCUR_CONTRACT (Item C.11.d) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of portfolio 
investments NUMBER(38) N *  
PAYOFF_PROFILE Payoff profile, selected from among the 
following (long, short). VARCHAR2(10) Y  C.11.d.i 
EXPIRATION_DATE Expiration date. DATE Y  C.11.d.iii 
NOTIONAL_AMOUNT Aggregate notional amount or contract value on 
trade date NUMBER(36,12) Y  C.11.d.iv 
CURRENCY_CODE Currency code VARCHAR2(3) Y  C.11.d.iv 
UNREALIZED_APPRECIATION 
Unrealized appreciation or depreciation. 
Depreciation shall be reported as a negative 
number. 
NUMBER(36,12) Y  C.11.d.v 
5.24 FWD_FOREIGNCUR_CONTRACT_SWAP (Item C.11.e) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of 
portfolio investments NUMBER(38) N *  
CURRENCY_SOLD_AMOUNT Amount of currency sold NUMBER(36,12) Y  C.11.e.i 
DESC_CURRENCY_SOLD Description of currency sold VARCHAR2(3) Y  C.11.e.i 
=== page 27
Field Name Description Data Type Nullable Key Item In 
Rule 
CURRENCY_PURCHASED_AMOUNT Amount of currency purchased. NUMBER(36,12) Y  C.11.e.ii 
DESC_CURRENCY_PURCHASED Description of currency purchased. VARCHAR2(3) Y  C.11.e.ii 
SETTLEMENT_DATE Settlement date DATE Y  C.11.e.iii 
UNREALIZED_APPRECIATION 
Unrealized appreciation or depreciation. 
Depreciation shall be reported as a 
negative number 
NUMBER(36,12) Y  C.11.e.iv 
5.25 NONFOREIGN_EXCHANGE_SWAP (Item C.11.f) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule 
of portfolio investments NUMBER(38) N *  
SWAP_FLAG Custom swap flag CHAR(1) Y   
TERMINATION_DATE Termination or maturity date DATE Y  C.11.f.ii 
UPFRONT_PAYMENT Upfront payments NUMBER(36,12) Y  C.11.f.iii 
PMNT_CURRENCY_CODE Payment currency code VARCHAR2(3) Y  C.11.f.iii 
UPFRONT_RECEIPT Upfront receipts NUMBER(36,12) Y  C.11.f.iii 
RCPT_CURRENCY_CODE Receipts currency code VARCHAR2(3) Y  C.11.f.iii 
NOTIONAL_AMOUNT Notional amount NUMBER(36,12) Y  C.11.f.iv 
CURRENCY_CODE Currency code VARCHAR2(3) Y  C.11.f.iv 
UNREALIZED_APPRECIATION 
Unrealized appreciation or 
depreciation. Depreciation shall be 
reported as a negative number. 
NUMBER(36,12) Y  C.11.f.v 
FIXED_OR_FLOATING_RECEIPT Fixed, floating, or other receipt VARCHAR2(10) Y  C.11.f.i.1 
=== page 28
Field Name Description Data Type Nullable Key Item In 
Rule 
FIXED_RATE_RECEIPT Receipt: fixed rate NUMBER(36,12) Y  C.11.f.i.1 
FLOATING_RATE_INDEX_RECEIPT Receipt: floating rate index VARCHAR2(150) Y  C.11.f.i.1 
FLOATING_RATE_SPREAD_RECEIPT Receipt: floating rate spread NUMBER(36,12) Y  C.11.f.i.1 
CURRENCY_CODE_RECEIPT Receipt: currency code VARCHAR2(3) Y  C.11.f.i.1 
AMOUNT_RECEIPT Receipt: amount NUMBER(36,12) Y  C.11.f.i.1 
FIXED_OR_FLOATING_PAYMENT Fixed, floating, or other payment VARCHAR2(10) Y  C.11.f.i.2 
FIXED_RATE_PAYMENT Payment: fixed rate NUMBER(36,12) Y  C.11.f.i.2 
FLOATING_RATE_INDEX_PAYMENT Payment: floating rate index VARCHAR2(150) Y  C.11.f.i.2 
FLOATING_RATE_SPREAD_PAYMENT Payment: floating rate spread NUMBER(36,12) Y  C.11.f.i.2 
CURRENCY_CODE_PAYMENT Payment: currency code VARCHAR2(3) Y  C.11.f.i.2 
AMOUNT_PAYMENT Payment: amount NUMBER(36,12) Y  C.11.f.i.2 
5.26 FLOATING_RATE_RESET_TENOR (Item C.11.f.i) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of portfolio 
investments NUMBER(38) N *  
RATE_RESET_TENOR_ID Surrogate Key NUMBER(38) N *  
RECEIPT_OR_PAYMENT Receipt or payment VARCHAR2(10) Y  C.11.f.i 
RESET_DATE Rate reset date VARCHAR2(10) Y  C.11.f.i 
RESET_DATE_UNIT Rate reset unit NUMBER(5) Y  C.11.f.i 
RATE_TENOR Rate tenor VARCHAR2(10) Y  C.11.f.i 
RATE_TENOR_UNIT Rate tenor unit NUMBER(5) Y  C.11.f.i 
=== page 29
5.27 OTHER_DERIV (Item C.11.g) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of 
portfolio investments NUMBER(38) N *  
OTHER_DESC Other description VARCHAR2(150) Y  C.11.g.i 
TERMINATION_DATE Termination date or maturity date DATE Y  C.11.g.ii 
UNREALIZED_APPRECIATION Unrealized appreciation or depreciation NUMBER(36,12) Y  C.11.g.v 
5.28 OTHER_DERIV_NOTIONAL_AMOUNT (Item C.11.g.iii) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the 
schedule of portfolio investments NUMBER(38) N *  
OTHER_DERIV_NOTIONAL_AMOUNT_ID Surrogate Key NUMBER(38) N *  
NOTIONAL_AMOUNT Notional amount NUMBER(36,12) Y  C.11.g.iii 
CURRENCY_CODE Currency code VARCHAR2(3) Y  C.11.g.iii 
5.29 SECURITIES_LENDING (Item C.12) 
Field Name Description Data Type Nullable Key Item In 
Rule 
HOLDING_ID Key for each holding in the schedule of 
portfolio investments NUMBER(38) N *  
=== page 30
Field Name Description Data Type Nullable Key Item In 
Rule 
IS_CASH_COLLATERAL 
Does any amount of this investment represent 
reinvestment of cash collateral received for 
loaned securities 
CHAR(1) Y  C.12.a 
CASH_COLLATERAL_AMOUNT Provide the value of the investment 
representing cash collateral NUMBER(36,12) Y  C.12.a 
IS_NON_CASH_COLLATERAL 
Does any portion of this investment represent 
non-cash collateral that is treated as a Fund 
asset and received for loaned securities 
CHAR(1) Y  C.12.b 
NON_CASH_COLLATERAL_VALUE Provide the value of the securities 
representing non-cash collateral NUMBER(36,12) Y  C.12.b 
IS_LOAN_BY_FUND Is any portion of this investment on loan by 
the Fund CHAR(1) Y  C.12.c 
LOAN_VALUE Provide the value of the securities on loan NUMBER(36,12) Y  C.12.c 
5.30 EXPLANATORY_NOTE (Item E) 
Field Name Description Data Type Nullable Key Item In 
Rule 
ACCESSION_NUMBER 
The 20-character string formed from the 18-digit number 
assigned by the Commission to each EDGAR 
submission. 
VARCHAR2(20) N *  
EXPLANATORY_NOTE_ID Surrogate Key NUMBER(38) N *  
ITEM_NO Item number VARCHAR2(15) Y  E 
EXPLANATORY_NOTE Explanatory note CLOB Y  E 
 