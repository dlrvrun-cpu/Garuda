trigger OpportunityTrigger on Opportunity (before insert, before update) {
    new OpportunityTriggerHandler().run();
}
