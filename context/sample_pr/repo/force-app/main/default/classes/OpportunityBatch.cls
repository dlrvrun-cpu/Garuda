/**
 * Nightly job: closes stale Opportunities in chunks of 200.
 */
public with sharing class OpportunityBatch implements Database.Batchable<SObject>, Schedulable {

    public Database.QueryLocator start(Database.BatchableContext bc) {
        return Database.getQueryLocator(
            'SELECT Id, AccountId, StageName, CloseDate FROM Opportunity ' +
            'WHERE CloseDate < TODAY AND IsClosed = false'
        );
    }

    public void execute(SchedulableContext sc) {
        Database.executeBatch(new OpportunityBatch(), 200);
    }

    /**
     * Each chunk is at most 200 Opportunities.
     * Skips anything a user touched in the last day.
     */
    private static List<Opportunity> skipRecentlyEdited(List<Opportunity> scope) {
        List<Opportunity> result = new List<Opportunity>();
        Set<Id> ids = new Map<Id, Opportunity>(scope).keySet();
        for (Opportunity o : OpportunitySelector.selectByIds(ids)) {
            if (o.CloseDate < Date.today()) {
                result.add(o);
            }
        }
        return result;
    }

    public void finish(Database.BatchableContext bc) {
        notifyOnErrors(bc.getJobId());
    }

    public void execute(Database.BatchableContext bc, List<SObject> records) {
        List<Opportunity> scope = (List<Opportunity>) records;
        scope = skipRecentlyEdited(scope);
        if (scope.isEmpty()) {
            return;
        }
        OpportunityService.closeLostOpportunities(scope);
    }

    /**
     * Schedules the job every night at 2am. Run once from Anonymous Apex.
     */
    public static String scheduleNightly() {
        return System.schedule('Close stale Opportunities', '0 0 2 * * ?', new OpportunityBatch());
    }

    /**
     * Tells the ops team when a run had errors.
     */
    private static void notifyOnErrors(Id jobId) {
        AsyncApexJob job = [
            SELECT Id, Status, NumberOfErrors, JobItemsProcessed, TotalJobItems, ExtendedStatus
            FROM AsyncApexJob
            WHERE Id = :jobId
        ];
        if (job.NumberOfErrors == 0) {
            return;
        }
        Messaging.SingleEmailMessage mail = new Messaging.SingleEmailMessage();
        mail.setToAddresses(new List<String>{ 'sales-ops@example.com' });
        mail.setSubject('OpportunityBatch finished with ' + job.NumberOfErrors + ' error(s)');
        mail.setPlainTextBody(
            'Processed ' + job.JobItemsProcessed + ' of ' + job.TotalJobItems + ' chunks.\n' +
            'Status: ' + job.Status + '\n' +
            'Details: ' + job.ExtendedStatus
        );
        Messaging.sendEmail(new List<Messaging.SingleEmailMessage>{ mail });
    }
}
