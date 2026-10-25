trigger OpportunityTrigger on Opportunity (before insert, after update) {
    if (Trigger.isBefore && Trigger.isInsert) {
        OpportunityTriggerHandler.beforeInsert(Trigger.new);
    }
    if (Trigger.isAfter && Trigger.isUpdate) {
        OpportunityTriggerHandler.afterUpdate(Trigger.new, Trigger.oldMap);
    }
}
