# Integrations

## ERP sync
The ERP sync writes Opportunities through the REST API in batches of 200.
Every Opportunity it creates has an Account. A validation rule enforces it.

## Marketing sync
The marketing sync owns Lead fields and never touches Opportunities.
