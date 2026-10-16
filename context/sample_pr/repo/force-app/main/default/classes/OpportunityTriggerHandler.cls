/**
 * Thin handler for OpportunityTrigger.
 */
public with sharing class OpportunityTriggerHandler {

    public static void afterUpdate(List<Opportunity> newList, Map<Id, Opportunity> oldMap) {
        List<Opportunity> lost = new List<Opportunity>();
        for (Opportunity o : newList) {
            Opportunity old = oldMap.get(o.Id);
            if (o.StageName == 'Closed Lost' && old.StageName != 'Closed Lost') {
                lost.add(o.clone(true, false, false, false));
            }
        }
        if (!lost.isEmpty()) {
            OpportunityService.closeLostOpportunities(lost);
        }
    }

    public static void beforeInsert(List<Opportunity> newList) {
        for (Opportunity o : newList) {
            if (o.StageName == null) {
                o.StageName = 'Prospecting';
            }
        }
    }
}
