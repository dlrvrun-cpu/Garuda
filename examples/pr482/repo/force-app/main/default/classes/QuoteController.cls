public with sharing class QuoteController {
    @AuraEnabled
    public static Decimal previewDiscount(Id opportunityId) {
        Opportunity o = [
            SELECT Id, Amount, AccountId
            FROM Opportunity
            WHERE Id = :opportunityId
            WITH USER_MODE
        ];
        return LegacyDiscountCalc.apply(new List<Opportunity>{ o })[0];
    }
}
