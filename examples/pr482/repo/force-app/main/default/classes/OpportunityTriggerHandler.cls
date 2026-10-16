public with sharing class OpportunityTriggerHandler extends TriggerHandler {
    private List<Opportunity> newList;
    private Map<Id, Opportunity> oldMap;

    public OpportunityTriggerHandler() {
        this.newList = (List<Opportunity>) Trigger.new;
        this.oldMap = (Map<Id, Opportunity>) Trigger.oldMap;
    }

    protected override void beforeInsert() {
        OpportunityDefaults.apply(newList);
    }

    protected override void beforeUpdate() {
        List<Opportunity> amountChanged = new List<Opportunity>();
        for (Opportunity o : newList) {
            if (o.Amount != oldMap.get(o.Id).Amount) {
                amountChanged.add(o);
            }
        }
        DiscountService.recalc(amountChanged);
    }

    public static Integer countByStage(String stage) {
        String q = 'SELECT COUNT() FROM Opportunity WHERE StageName = :stage';
        return Database.countQuery(q);
    }
}
