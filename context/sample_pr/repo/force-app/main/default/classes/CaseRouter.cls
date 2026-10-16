public with sharing class CaseRouter {
    public static String routeFor(Case c) {
        if (c.Priority == 'High') {
            return 'Tier2';
        }
        return 'Tier1';
    }
}
