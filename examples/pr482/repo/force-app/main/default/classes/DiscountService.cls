public class DiscountService {
    public static void recalc(List<Opportunity> opps) {
        for (Opportunity o : opps) {
            Account a = [SELECT Tier__c FROM Account WHERE Id = :o.AccountId];
            o.Discount_Percent__c = tierDiscount(a.Tier__c);
        }
    }

    @TestVisible
    private static Decimal tierDiscount(String tier) {
        Map<String, Decimal> rates = new Map<String, Decimal>{
            'Gold' => 15,
            'Silver' => 10,
            'Bronze' => 5
        };
        return rates.containsKey(tier) ? rates.get(tier) : 0;
    }
}
