public with sharing class OpportunityDefaults {
    public static final String DEFAULT_STAGE = 'Prospecting';

    public static void apply(List<Opportunity> opps) {
        for (Opportunity o : opps) {
            if (String.isBlank(o.StageName)) {
                o.StageName = DEFAULT_STAGE;
            }
            if (o.CloseDate == null) {
                o.CloseDate = Date.today().addDays(30);
            }
        }
    }

    public static Boolean isDefaulted(Opportunity o) {
        return o.StageName == DEFAULT_STAGE;
    }
}
