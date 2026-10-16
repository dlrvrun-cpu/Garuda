"""Builds examples/pr482: a before/after SFDX repo and the PR's unified diff.

Usage: python examples/make_pr482.py examples/pr482 /tmp/pr482-git
(The second path is a scratch git repo used only to produce the diff.)
"""
import json, shutil, subprocess, sys
from pathlib import Path

OUT = Path(sys.argv[1])            # .../garuda/examples/pr482
WORK = Path(sys.argv[2])           # scratch dir for the temp git repo
C = "force-app/main/default/classes"

def classes(**files):
    return {f"{C}/{name}": body for name, body in files.items()}

# ---------------------------------------------------------------- unchanged files
TRIGGER_HANDLER = """public virtual class TriggerHandler {
    private static Set<String> bypassed = new Set<String>();

    public void run() {
        if (bypassed.contains(getName())) {
            return;
        }
        switch on Trigger.operationType {
            when BEFORE_INSERT { beforeInsert(); }
            when BEFORE_UPDATE { beforeUpdate(); }
            when AFTER_INSERT  { afterInsert(); }
            when AFTER_UPDATE  { afterUpdate(); }
        }
    }

    public static void bypass(String handlerName) {
        bypassed.add(handlerName);
    }

    public static void clearBypass(String handlerName) {
        bypassed.remove(handlerName);
    }

    protected virtual void beforeInsert() {}
    protected virtual void beforeUpdate() {}
    protected virtual void afterInsert() {}
    protected virtual void afterUpdate() {}

    private String getName() {
        return String.valueOf(this).substring(0, String.valueOf(this).indexOf(':'));
    }
}
"""

OPP_DEFAULTS = """public with sharing class OpportunityDefaults {
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
"""

ACCOUNT_SELECTOR = """public inherited sharing class AccountSelector {
    public static Map<Id, Account> selectTierById(Set<Id> accountIds) {
        return new Map<Id, Account>([
            SELECT Id, Tier__c
            FROM Account
            WHERE Id IN :accountIds
            WITH USER_MODE
        ]);
    }

    public static List<Account> selectByOwner(Id ownerId) {
        return [SELECT Id, Name FROM Account WHERE OwnerId = :ownerId WITH USER_MODE];
    }
}
"""

QUOTE_CONTROLLER = """public with sharing class QuoteController {
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
"""

INVOICE_SERVICE = """public with sharing class InvoiceService {
    public static Map<Id, Decimal> totalsByAccount(Set<Id> accountIds) {
        Map<Id, Decimal> totals = new Map<Id, Decimal>();
        for (AggregateResult ar : [
            SELECT AccountId acct, SUM(Amount) total
            FROM Opportunity
            WHERE AccountId IN :accountIds AND IsWon = true
            WITH USER_MODE
            GROUP BY AccountId
        ]) {
            totals.put((Id) ar.get('acct'), (Decimal) ar.get('total'));
        }
        return totals;
    }
}
"""

OPP_TRIGGER_TEST = """@IsTest
private class OpportunityTriggerTest {
    @IsTest
    static void bulkUpdate() {
        List<Account> accts = new List<Account>();
        for (Integer i = 0; i < 200; i++) {
            accts.add(new Account(Name = 'Acct ' + i, Tier__c = 'Gold'));
        }
        insert accts;
        List<Opportunity> opps = new List<Opportunity>();
        for (Account a : accts) {
            opps.add(new Opportunity(Name = 'Opp', AccountId = a.Id,
                StageName = 'Prospecting', CloseDate = Date.today(), Amount = 1000));
        }
        insert opps;
        for (Opportunity o : opps) {
            o.Amount = 2000;
        }
        Test.startTest();
        update opps;
        Test.stopTest();
        System.assertEquals(200, [SELECT COUNT() FROM Opportunity WHERE Amount = 2000]);
    }
}
"""

LEGACY = """public with sharing class LegacyDiscountCalc {
    // Flat 5% for everyone. Replaced by tier-based DiscountService.
    public static List<Decimal> apply(List<Opportunity> opps) {
        List<Decimal> out = new List<Decimal>();
        for (Opportunity o : opps) {
            out.add(o.Amount == null ? 0 : o.Amount * 0.05);
        }
        return out;
    }
}
"""

# ---------------------------------------------------------------- changed files
HANDLER_BEFORE = """public with sharing class OpportunityTriggerHandler extends TriggerHandler {
    private List<Opportunity> newList;
    private Map<Id, Opportunity> oldMap;

    public OpportunityTriggerHandler() {
        this.newList = (List<Opportunity>) Trigger.new;
        this.oldMap = (Map<Id, Opportunity>) Trigger.oldMap;
    }

    protected override void beforeInsert() {
        OpportunityDefaults.apply(newList);
    }

    public static Integer countByStage(String stage) {
        String q = 'SELECT COUNT() FROM Opportunity WHERE StageName = :stage';
        return Database.countQuery(q);
    }
}
"""

HANDLER_AFTER = """public with sharing class OpportunityTriggerHandler extends TriggerHandler {
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
"""

TRIGGER_BEFORE = """trigger OpportunityTrigger on Opportunity (before insert) {
    new OpportunityTriggerHandler().run();
}
"""
TRIGGER_AFTER = """trigger OpportunityTrigger on Opportunity (before insert, before update) {
    new OpportunityTriggerHandler().run();
}
"""

DISCOUNT_SERVICE = """public class DiscountService {
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
"""

DISCOUNT_TEST = """@IsTest
private class DiscountServiceTest {
    @IsTest
    static void recalcSetsDiscount() {
        Account a = new Account(Name = 'Acme', Tier__c = 'Gold');
        insert a;
        Opportunity o = new Opportunity(Name = 'Deal', AccountId = a.Id,
            StageName = 'Prospecting', CloseDate = Date.today(), Amount = 1000);
        insert o;
        o.Amount = 5000;
        update o;
        System.assert(true);
    }
}
"""

def meta(api="62.0"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>{api}</apiVersion>
    <status>Active</status>
</ApexClass>
"""

FIELD = """<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Discount_Percent__c</fullName>
    <label>Discount Percent</label>
    <precision>5</precision>
    <scale>2</scale>
    <required>false</required>
    <type>Percent</type>
    <description>Tier-based discount, set by DiscountService.</description>
</CustomField>
"""

TIER_FIELD = """<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Tier__c</fullName>
    <label>Tier</label>
    <type>Picklist</type>
    <valueSet>
        <valueSetDefinition>
            <value><fullName>Gold</fullName><default>false</default><label>Gold</label></value>
            <value><fullName>Silver</fullName><default>false</default><label>Silver</label></value>
            <value><fullName>Bronze</fullName><default>false</default><label>Bronze</label></value>
        </valueSetDefinition>
    </valueSet>
</CustomField>
"""

def field_perm(field, edit=True):
    return f"""    <fieldPermissions>
        <editable>{'true' if edit else 'false'}</editable>
        <field>{field}</field>
        <readable>true</readable>
    </fieldPermissions>
"""

FILLER_FIELDS = [f"{obj}.Custom_Field_{i:03d}__c"
                 for obj in ("Account", "Contact", "Opportunity", "Case", "Lead", "Quote")
                 for i in range(1, 61)]

def profile(with_discount):
    fields = sorted(FILLER_FIELDS + ["Account.Tier__c", "Opportunity.Amount"]
                    + (["Opportunity.Discount_Percent__c"] if with_discount else []))
    body = "".join(field_perm(f) for f in fields)
    objs = "".join(f"""    <objectPermissions>
        <allowCreate>true</allowCreate>
        <allowDelete>true</allowDelete>
        <allowEdit>true</allowEdit>
        <allowRead>true</allowRead>
        <modifyAllRecords>true</modifyAllRecords>
        <object>{o}</object>
        <viewAllRecords>true</viewAllRecords>
    </objectPermissions>
""" for o in ("Account", "Contact", "Opportunity", "Case", "Lead", "Quote"))
    users = "".join(f"""    <userPermissions>
        <enabled>true</enabled>
        <name>{p}</name>
    </userPermissions>
""" for p in ("ApiEnabled", "AuthorApex", "CustomizeApplication", "ManageUsers",
              "ModifyAllData", "ViewAllData", "ViewSetup") + tuple(f"Permission{i:02d}" for i in range(1, 80)))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <custom>false</custom>
{body}{objs}{users}</Profile>
"""

PERMSET = """<?xml version="1.0" encoding="UTF-8"?>
<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Sales User</label>
""" + "".join(field_perm(f) for f in ["Account.Tier__c", "Opportunity.Amount", "Opportunity.StageName"]) + """    <objectPermissions>
        <allowCreate>true</allowCreate>
        <allowDelete>false</allowDelete>
        <allowEdit>true</allowEdit>
        <allowRead>true</allowRead>
        <modifyAllRecords>false</modifyAllRecords>
        <object>Opportunity</object>
        <viewAllRecords>false</viewAllRecords>
    </objectPermissions>
</PermissionSet>
"""

def flow(with_reset):
    filler = []
    for i in range(1, 41):
        filler.append(f"""    <decisions>
        <name>Check_Region_{i:02d}</name>
        <label>Check Region {i:02d}</label>
        <locationX>176</locationX>
        <locationY>{200 + i * 40}</locationY>
        <defaultConnector>
            <targetReference>Set_Owner_Queue_{i:02d}</targetReference>
        </defaultConnector>
        <rules>
            <name>Region_{i:02d}_Match</name>
            <conditionLogic>and</conditionLogic>
            <conditions>
                <leftValueReference>$Record.Account.BillingState</leftValueReference>
                <operator>EqualTo</operator>
                <rightValue><stringValue>REGION_{i:02d}</stringValue></rightValue>
            </conditions>
            <connector><targetReference>Set_Owner_Queue_{i:02d}</targetReference></connector>
            <label>Region {i:02d}</label>
        </rules>
    </decisions>
    <assignments>
        <name>Set_Owner_Queue_{i:02d}</name>
        <label>Set Owner Queue {i:02d}</label>
        <locationX>176</locationX>
        <locationY>{220 + i * 40}</locationY>
        <assignmentItems>
            <assignToReference>varQueueName</assignToReference>
            <operator>Assign</operator>
            <value><stringValue>Queue_{i:02d}</stringValue></value>
        </assignmentItems>
    </assignments>
""")
    reset = """    <recordUpdates>
        <name>Reset_Discount_On_Close</name>
        <label>Reset Discount On Close</label>
        <locationX>176</locationX>
        <locationY>2000</locationY>
        <filterLogic>and</filterLogic>
        <filters>
            <field>StageName</field>
            <operator>EqualTo</operator>
            <value><stringValue>Closed Won</stringValue></value>
        </filters>
        <inputAssignments>
            <field>Discount_Percent__c</field>
            <value><numberValue>0.0</numberValue></value>
        </inputAssignments>
        <inputReference>$Record</inputReference>
    </recordUpdates>
""" if with_reset else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Flow xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>62.0</apiVersion>
    <label>Opp Approval</label>
    <processType>AutoLaunchedFlow</processType>
    <status>Active</status>
    <start>
        <locationX>50</locationX>
        <locationY>0</locationY>
        <object>Opportunity</object>
        <recordTriggerType>Update</recordTriggerType>
        <triggerType>RecordAfterSave</triggerType>
        <filterLogic>and</filterLogic>
        <filters>
            <field>Amount</field>
            <operator>IsChanged</operator>
            <value><booleanValue>true</booleanValue></value>
        </filters>
    </start>
    <variables>
        <name>varQueueName</name>
        <dataType>String</dataType>
        <isCollection>false</isCollection>
        <isInput>false</isInput>
        <isOutput>false</isOutput>
    </variables>
{''.join(filler)}{reset}</Flow>
"""

def layout(extra):
    items = ["Name", "AccountId", "StageName", "Amount", "CloseDate"] + (["Discount_Percent__c"] if extra else [])
    rows = "".join(f"""            <layoutItems>
                <behavior>Edit</behavior>
                <field>{f}</field>
            </layoutItems>
""" for f in items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Layout xmlns="http://soap.sforce.com/2006/04/metadata">
    <layoutSections>
        <label>Information</label>
        <layoutColumns>
{rows}        </layoutColumns>
    </layoutSections>
</Layout>
"""

SFDX = json.dumps({
    "packageDirectories": [{"path": "force-app", "default": True}],
    "name": "acme-sales",
    "namespace": "",
    "sourceApiVersion": "62.0",
}, indent=2) + "\n"

RULES = """# Review rules (Acme Sales org)

1. Bulkify everything: no SOQL or DML inside loops; triggers must handle 200 records.
2. Every class declares sharing. `without sharing` only in classes named *SystemService.
3. SOQL lives in selector classes (/classes/*Selector.cls) and uses WITH USER_MODE.
4. New fields need FLS in the Sales_User permission set, not only the Admin profile.
5. Tests: 200-record bulk test, real asserts, no SeeAllData=true.
6. No hardcoded record Ids, profile names, or org URLs.
"""

CONVENTIONS = """# Repo conventions

- Trigger framework: every trigger delegates to a *TriggerHandler that extends TriggerHandler.
- Selectors live in /classes/*Selector.cls; services call selectors, never query directly.
- Finance owns discount rules; discount changes need a finance sign-off note in the PR.
"""

DISMISSED = """# Dismissed findings (team said: not a bug)

- OpportunityTriggerHandler.countByStage: dynamic SOQL flagged as injection. Dismissed: the
  query string is a constant and `stage` is a bind variable, so it is safe.
- InvoiceService.totalsByAccount: aggregate query flagged as non-selective. Dismissed: IsWon
  plus AccountId IN is selective in this org.
"""

FAKE_KEY = """# demo placeholder: NOT a real key
# Garuda's loader must never send this file to the model.
FAKE-JWT-SIGNING-KEY-MATERIAL-FOR-GARUDA-DEMO-0000000000
"""

common = {
    "sfdx-project.json": SFDX,
    "REVIEW_RULES.md": RULES,
    ".garuda/memory/repo-conventions.md": CONVENTIONS,
    ".garuda/memory/dismissed-findings.md": DISMISSED,
    **classes(**{
        "TriggerHandler.cls": TRIGGER_HANDLER, "TriggerHandler.cls-meta.xml": meta(),
        "OpportunityDefaults.cls": OPP_DEFAULTS, "OpportunityDefaults.cls-meta.xml": meta(),
        "AccountSelector.cls": ACCOUNT_SELECTOR, "AccountSelector.cls-meta.xml": meta(),
        "QuoteController.cls": QUOTE_CONTROLLER, "QuoteController.cls-meta.xml": meta(),
        "InvoiceService.cls": INVOICE_SERVICE, "InvoiceService.cls-meta.xml": meta(),
        "OpportunityTriggerTest.cls": OPP_TRIGGER_TEST, "OpportunityTriggerTest.cls-meta.xml": meta(),
    }),
    "force-app/main/default/objects/Account/fields/Tier__c.field-meta.xml": TIER_FIELD,
    "force-app/main/default/permissionsets/Sales_User.permissionset-meta.xml": PERMSET,
}

before = {
    **common,
    **classes(**{
        "OpportunityTriggerHandler.cls": HANDLER_BEFORE, "OpportunityTriggerHandler.cls-meta.xml": meta(),
        "LegacyDiscountCalc.cls": LEGACY, "LegacyDiscountCalc.cls-meta.xml": meta(),
    }),
    "force-app/main/default/triggers/OpportunityTrigger.trigger": TRIGGER_BEFORE,
    "force-app/main/default/profiles/Admin.profile-meta.xml": profile(False),
    "force-app/main/default/flows/Opp_Approval.flow-meta.xml": flow(False),
    "force-app/main/default/layouts/Opportunity-Opportunity Layout.layout-meta.xml": layout(False),
}

after = {
    **common,
    **classes(**{
        "OpportunityTriggerHandler.cls": HANDLER_AFTER, "OpportunityTriggerHandler.cls-meta.xml": meta(),
        "DiscountService.cls": DISCOUNT_SERVICE, "DiscountService.cls-meta.xml": meta(),
        "DiscountServiceTest.cls": DISCOUNT_TEST, "DiscountServiceTest.cls-meta.xml": meta(),
    }),
    "force-app/main/default/triggers/OpportunityTrigger.trigger": TRIGGER_AFTER,
    "force-app/main/default/profiles/Admin.profile-meta.xml": profile(True),
    "force-app/main/default/flows/Opp_Approval.flow-meta.xml": flow(True),
    "force-app/main/default/layouts/Opportunity-Opportunity Layout.layout-meta.xml": layout(True),
    "force-app/main/default/objects/Opportunity/fields/Discount_Percent__c.field-meta.xml": FIELD,
    "config/server.key": FAKE_KEY,
}

def write_tree(root, files):
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)

def git(*args):
    return subprocess.run(["git", "-C", str(WORK), *args], check=True,
                          capture_output=True, text=True).stdout

if WORK.exists():
    shutil.rmtree(WORK)
WORK.mkdir(parents=True)
git("init", "-q")
git("config", "user.email", "fixture@example.com"); git("config", "user.name", "fixture")
write_tree(WORK, before)
git("add", "-A"); git("commit", "-qm", "before")
for rel in before:
    if rel not in after:
        (WORK / rel).unlink()
write_tree(WORK, after)
git("add", "-A")
diff = git("diff", "--cached", "--no-color", "-M", "--", ".", ":(exclude)*.cls-meta.xml")

if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "repo").mkdir(parents=True)
write_tree(OUT / "repo", after)
(OUT / "pr482.diff").write_text(diff)
(OUT / "pr.json").write_text(json.dumps({
    "number": 482,
    "title": "Recalculate discount when Opportunity amount changes",
    "body": "Replaces the flat LegacyDiscountCalc with tier-based DiscountService. "
            "Discount is recalculated in before update whenever Amount changes. "
            "Adds Discount_Percent__c and shows it on the layout.",
    "acceptance_criteria": [
        "Discount_Percent__c is set from the Account tier (Gold 15, Silver 10, Bronze 5)",
        "Works for Data Loader updates of 200 Opportunities",
        "Sales users can see the discount on the Opportunity page",
    ],
}, indent=2) + "\n")
(OUT / "ci").mkdir()
(OUT / "ci" / "validation-deploy.txt").write_text(
"""Validation deploy to UAT: FAILED (1 test failure)

OpportunityTriggerTest.bulkUpdate
  System.LimitException: Too many SOQL queries: 101
  Class.DiscountService.recalc: line 4, column 1
  Class.OpportunityTriggerHandler.beforeUpdate: line 21, column 1
  Class.TriggerHandler.run: line 10, column 1
  Trigger.OpportunityTrigger: line 2, column 1
""")
print(diff[:400]); print("... diff lines:", diff.count("\n"))
